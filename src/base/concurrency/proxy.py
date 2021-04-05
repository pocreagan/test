from collections import deque
from dataclasses import dataclass
from functools import wraps
from inspect import cleandoc
from inspect import signature
from inspect import Signature
from itertools import chain
from queue import Empty
from queue import Queue
from threading import Event
from threading import Thread
from time import sleep
from time import time
from typing import Any
from typing import Callable
from typing import Deque
from typing import Dict
from typing import Generator
from typing import List
from typing import Optional
from typing import Tuple
from typing import TypeVar

# noinspection SpellCheckingInspection
from src.base import atexit_proxy as atexit
from src.base.concurrency.concurrency import make_duplex_connection
from src.base.concurrency.concurrency import SYNC_COMM_ERROR_T
from src.base.concurrency.concurrency import ThreadConnection
from src.base.decorators import cached_property
from src.base.general import setdefault_attr_from_factory
from src.base.log import logger

__all__ = [
    'Mixin',
    'Promise',
    'exposed',
    'exposed_directly',
    'CancelledError',
    'PromiseError',
    'ProxyError',
]

log = logger(__name__)


class PromiseError(Exception):
    pass


class ProxyError(Exception):
    pass


class CancelledError(Exception):
    pass


_SCHEDULER_CALLBACK_T = Callable[[], None]
_return_value_key = '_cached_promise_results'
_NOTHING = object()


@dataclass
class Task:
    """
    represents one method promise issued to _ProxyServer.
    """
    f: str
    args: tuple
    kwargs: dict
    execute_at: float
    returned = _NOTHING
    te: Optional[float] = None
    exception: Optional[Exception] = None

    @property
    def is_done(self) -> bool:
        return self.returned is not _NOTHING

    @property
    def time_remaining(self) -> float:
        return max(time() - self.execute_at, 0.)

    @property
    def return_value(self):
        if self.exception is None:
            return self.returned
        raise self.exception

    def perform(self, instance) -> bool:
        """
        the only exceptions which are not bottled up here are the ones raised by .check_guard
        everything else is reraised on Task.resolve()
        because they need to bubble up the _ProxyServer's .poll for handling
        ::return:: is used in .__perform_task() -> self.completed
        """
        _ti = time()
        try:
            self.returned = getattr(instance, self.f)(*self.args, **self.kwargs)

        except Exception as e:
            self.returned = None
            self.exception = e
            return False

        else:
            return True

        finally:
            self.te = time() - _ti

    def resolve(self, q: ThreadConnection, timeout: float = None) -> 'Task':
        """
        returns whether the task was completed regardless of exception state
        """
        if not self.is_done:
            try:
                returned_task = q.get(timeout)

            except Empty:
                raise PromiseError(f'{self} timeout')

            else:
                for attr in ['returned', 'exception', 'te']:
                    setattr(self, attr, getattr(returned_task, attr))

        return self


def _guard_promise_not_cancelled(f: Callable):
    @wraps(f)
    def inner(self: 'Promise', *args, **kwargs):
        if self.cancelled:
            raise PromiseError('cannot resolve a _cancelled Promise')
        return f(self, *args, **kwargs)

    return inner


class Promise:
    """
    represents one or more _tasks issued to _ProxyServer.

    there are two ways to decide when to resolve a promise object:
        - .resolve(timeout=float)
            PromiseTimeoutError must be handled on timeout being reached
        - for result in promise:
            ...
            iterate through _tasks, resolving each in order

    if Promise wraps one task, it resolves to the return value of that one task
    if it wraps more than one task, it resolves to a list of their return values in execution order

    ! all exceptions are caught in _ProxyServer and reraised as-is in .resolve()'s thread.
    """
    proxy: 'Mixin'

    def __init__(self, tasks: Generator[Task, None, None]) -> None:
        self._tasks = list(tasks)
        self._cancelled = False
        self._resolved = False

    def poll(self) -> bool:
        try:
            self.resolve(0.)
        except PromiseError:
            return False
        return True

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    @property
    def resolved(self) -> bool:
        return self._resolved

    def __mark_resolved(self) -> None:
        self._resolved = True
        setattr(self.proxy, _promise_outstanding_key, False)

    def __mark_cancelled(self) -> None:
        self._cancelled = True
        setattr(self.proxy, _promise_outstanding_key, False)

    @property
    @_guard_promise_not_cancelled
    def results(self):
        if not self.resolved:
            raise PromiseError('Promise not yet resolved')

        return_value = getattr(self, _return_value_key, None)
        if return_value is None:
            results = [task.return_value for task in self._tasks]
            if len(results) == 1:
                results = results[0]

            setattr(self, _return_value_key, results)
            return results
        return return_value

    @_guard_promise_not_cancelled
    def resolve(self, timeout: float = None):
        if not self.resolved:

            ti = time()
            for task in self._tasks:
                # noinspection PyStatementEffect
                task.resolve(self.proxy.proxy_q, None if timeout is None else ti - timeout).return_value

            self.__mark_resolved()

        return self.results

    def cancel(self) -> None:
        if not self.resolved:
            self.proxy.proxy_cancel_flag.set()
            self.__mark_cancelled()

    def __iter__(self) -> 'Promise':
        if len(self._tasks) == 1:
            raise TypeError('cannot iterate over a Promise for one task')

        self._i = -1
        return self

    @_guard_promise_not_cancelled
    def __next__(self) -> Any:
        self._i += 1
        try:
            task = self._tasks[self._i]

        except IndexError:
            self.__mark_resolved()
            raise StopIteration

        else:
            return task.resolve(self.proxy.proxy_q).return_value


_cancel_flat_T = Event
_q_T = ThreadConnection
_SYNC_OBJECTS_T = Tuple[_q_T, _cancel_flat_T]


class _SyncMixin:
    proxy_cancel_flag: _cancel_flat_T
    proxy_q: _q_T
    proxy_resource: Any


def _make_synchronization_objects() -> Tuple[_SYNC_OBJECTS_T, _SYNC_OBJECTS_T]:
    q1, q2 = Queue(), Queue()
    (c1, c2), flag = make_duplex_connection(_q_T, q1, q2, q2, q1), _cancel_flat_T()
    return (c1, flag), (c2, flag)


def _proxy_init(instance, resource, q, cancel_flag) -> None:
    instance.proxy_resource, instance.proxy_q = resource, q
    instance.proxy_cancel_flag = cancel_flag


class _ProxyServer(Thread, _SyncMixin):
    """
    _tasks are prioritized with a min-heap, which compares on the following values in decreasing importance:
         - task.execute_at
         - task.priority
         - strictly increasing class-private counter <--- ensures sort stability
    """
    resource: Optional['Mixin']

    def __schedule(self, task: Task) -> None:
        self._scheduled_tasks.append(task)
        self._next_task_t = self._scheduled_tasks[0].execute_at

    @property
    def __time_before_next_task(self) -> Optional[float]:
        """
        this is only used as the Queue.get() timeout arg
        returns 0. at minimum
        returns None when there are no scheduled _tasks -> Queue.get(timeout=None)
        """
        if self._scheduled_tasks:
            return max((self._next_task_t - time()) - .001, 0.)
            # " - .001" is a fudge factor to keep the poll loop tight
            #     when a task is approximately scheduled to start

    def __pick_scheduled_task(self) -> Optional[Task]:
        if self._next_task_t and time() >= self._next_task_t:
            next_task = self._scheduled_tasks.popleft()
            self._next_task_t = self._scheduled_tasks[0].execute_at if self._scheduled_tasks else None
            return next_task

    def __init__(self, *sync_args) -> None:
        Thread.__init__(
            self, target=self.__main, name=type(self).__qualname__,
            daemon=True, args=(*sync_args,),
        )

    def __perform_one_scheduled_task(self) -> bool:
        """
        get earliest scheduled task and execute it if it's time to do so
        enqueues Message.Notification if any
        return whether a task has been completed
        """
        if self.proxy_cancel_flag.is_set():
            self._scheduled_tasks.clear()
            self.proxy_cancel_flag.clear()

        if self._scheduled_tasks:

            task = self.__pick_scheduled_task()
            if task:
                if not task.perform(self.proxy_resource):
                    self._scheduled_tasks.clear()

                self.proxy_q.put(task)
                return True

        return False

    def __poll(self) -> None:
        try:
            task: Task = self.proxy_q.get(timeout=self.__time_before_next_task)

        except Empty:
            if not self.__perform_one_scheduled_task():
                sleep(0.)

        else:
            self.__schedule(task)

    def __main(self, *sync_args) -> None:
        _proxy_init(self, *sync_args)

        _name = type(self).__name__
        self._next_task_t: Optional[float] = None
        self._scheduled_tasks: Deque[Task] = deque()
        log.info(f'{_name}: spawned')

        try:
            while 1:
                self.__poll()

        except CancelledError:
            pass

        except SYNC_COMM_ERROR_T:
            self._scheduled_tasks.clear()

        log.info(f'{_name}: joined')
        self.proxy_q.put_sentinel()


def _builder(field: str, method_names: Tuple[str, ...] = None, pass_through: bool = False):
    def outer(f: Callable[['exposed'], 'exposed']) -> Callable[..., 'exposed']:
        _method_name = f.__name__
        s1_ = ' | '.join(map(lambda name: f'.{name}()', method_names or (_method_name,)))
        s1_ += ' should be called once / request'
        s2_ = f'{_method_name} set {field} to None'

        @wraps(f)
        def inner(instance: 'exposed', *args, **kwargs):
            # noinspection PyProtectedMember
            if getattr(instance, field, None) is not None or instance._do_now:
                raise PromiseError(s1_)

            if pass_through:
                value = args[0]
            else:
                # noinspection PyArgumentList
                value = f(instance, *args, **kwargs)

            if value is None:
                instance.instance.warn(s2_)

            setattr(instance, field, value)
            return instance

        return inner

    return outer


_DECORATED_METHOD_T = TypeVar('_DECORATED_METHOD_T', bound=Callable)
_promise_outstanding_key = '_proxy_promise_outstanding'


# noinspection PyPep8Naming
class exposed_directly:
    """
       class BaseClass(..., proxy.Mixin):
            @exposed_directly
            def _(self, ...): ...
                - always blocks and returns as normal, including when called on an object proxy
    """
    registry_key = '_exposed_method_registry_proxy_only'

    def __init__(self, f: Callable) -> None:
        self._f = f

    def __set_name__(self, owner, name):
        setdefault_attr_from_factory(owner, self.registry_key, dict)[name] = self
        setattr(owner, name, self._f)

    def __get__(self, instance, owner) -> Callable:
        """provided for static type checker"""


# noinspection PyPep8Naming
class exposed:
    """
    class BaseClass(..., proxy.Mixin):
        @exposed
        def method(self, ...) <no return annotation here> : ...
            - issues task to proxy server and returns Promise

        def _(self, ...): ...
            - raises RuntimeError when called on a proxy resource

    - if _ProxyServer is not servicing self, calls as normal, blocking and returning.
    - method_names like .at() and .after() will raise an error if used in this situation.

    - if server is servicing self:
        builds _tasks,
        enqueues them to the promise keeper thread,
        returns them unfulfilled as a Promise object,

    self.<method>.at:                - see method docs.
    self.<method>.after:             - see method docs.

    task metadata are reset on each method call

    adds self to owning class's __dict__[exposed.class_dict_key] as a hook for other class-level manipulations
    .args_spec and .doc are cached on the object for convenience
    """
    registry_key = '_exposed_method_registry_'

    _task_times: Optional[Tuple[float, ...]]
    _check_callback: Optional[_SCHEDULER_CALLBACK_T]

    @cached_property
    def args_spec(self) -> Signature:
        return signature(self._f)

    @cached_property
    def doc(self) -> Optional[str]:
        if self._f.__doc__ is not None:
            return cleandoc(self._f.__doc__)

    def _clear_metadata(self) -> None:
        self._task_times = None

    def __init__(self, f: Callable) -> None:
        self._f = f
        self._do_now = False
        wraps(f)(self)
        self._clear_metadata()

    def __set_name__(self, owner, name):
        setdefault_attr_from_factory(owner, self.registry_key, dict)[name] = self
        self.owner, self.name = owner, name

    def __get__(self, instance, owner: type) -> Callable:
        self.instance = instance
        self.owner = owner
        self._do_now = False
        return self

    def __make_task(self, args, kwargs, t: float) -> 'Task':
        self.instance.proxy_q.put(Task(self.name, args, kwargs, t))
        return Task(self.name, args, kwargs, t)

    def __make_promise(self, args, kwargs) -> Promise:
        if getattr(self.instance, _promise_outstanding_key, False):
            raise PromiseError('cannot issue new promise until current one is _resolved or _cancelled')
        promise = Promise(self.__make_task(args, kwargs, t) for t in (self._task_times or (time(),)))
        promise.proxy = self.instance
        self._clear_metadata()
        setattr(self.instance, _promise_outstanding_key, True)
        return promise

    def __call__(self, *args, **kwargs):
        if getattr(self.instance, 'proxy_resource', None):
            promise = self.__make_promise(args, kwargs)
            if self._do_now:
                return promise.resolve()
            return promise

        # SUPPRESS-LINTER <.__get__ is a member of any decorated method>
        # methods all implement the descriptor base out of the box
        # noinspection PyUnresolvedReferences
        setattr(self.instance, self.name, self._f.__get__(self.instance, self.owner))
        return getattr(self.instance, self.name)(*args, **kwargs)

    @_builder('_task_times', ('at', 'after'))
    def after(self, *times: float, from_: float = None) -> 'exposed':
        """
        requests underlying method at intervals from now, or from ::from_::, if provided
        """
        # noinspection PyTypeChecker
        return sorted(map((from_ or time()).__add__, times)) or None

    @_builder('_task_times', ('at', 'after', 'on_interval'))
    def at(self, *times: float) -> 'exposed':
        """
        requests underlying method at provided timestamps
        """
        # noinspection PyTypeChecker
        return sorted(times) or None

    @_builder('_task_times', ('at', 'after', 'on_interval'))
    def on_interval(self, interval: float, n: int, from_: float = None) -> 'exposed':
        """
        requests underlying method at provided timestamps
        """
        # noinspection PyTypeChecker
        return list(map((from_ or time()).__add__, [(i + 1) * interval for i in range(n)])) or None

    def now(self) -> 'exposed':
        if self._task_times:
            raise PromiseError('can only call .now() without .after(), .at(), or .on_interval()')
        self._do_now = True
        return self


_T = TypeVar('_T')
_CALLABLE_T = TypeVar('_CALLABLE_T', bound=Callable)


class Mixin(_SyncMixin):
    __make_proxy_cache_key = '_proxy_type_cache'
    _proxy_flags: List[Event] = None

    # this is produced on proxy spawn and consumed in exposed.__get__
    resource: Optional['_ProxyServer']

    @staticmethod
    def __make_private_method(class_name: str, f: _CALLABLE_T) -> _CALLABLE_T:
        @wraps(f)
        def inner(*args, **kwargs):
            _ = args, kwargs
            raise ProxyError(f'{class_name}.{f.__name__} is not exposed on proxy')

        return inner  # type: ignore

    def __make_proxy(self, proxy_server: _ProxyServer) -> 'Mixin':
        """
        make proxy class by dynamic subclassing
        this proxy class is cached on the owning class
        substitute __init__() with _proxy_init()
        substitute non-exposed methods with a function that raises ProxyError
        instantiate proxy object and return it
        the proxy object is not cached
        """
        cls = type(self)
        class_name = cls.__name__
        proxy_type = getattr(cls, self.__make_proxy_cache_key, None)
        if not proxy_type:

            proxy_type = type(cls.__name__ + '_PROXY', (cls,), {})  # type: ignore
            setattr(proxy_type, '__init__', _proxy_init)

            registry_exposed: Dict = getattr(proxy_type, exposed.registry_key, {})
            registry_proxy_only: Dict = getattr(proxy_type, exposed_directly.registry_key, {})
            registry = set(chain(registry_exposed.keys(), registry_proxy_only.keys()))

            for cla in proxy_type.__mro__:
                for k, v in cla.__dict__.items():
                    if callable(v) and not k.startswith('__'):
                        if k not in registry:
                            setattr(proxy_type, k, self.__make_private_method(class_name, v))

            setattr(cls, self.__make_proxy_cache_key, proxy_type)

        return proxy_type(proxy_server, self.proxy_q, self.proxy_cancel_flag)  # type: ignore

    _Mix_T = TypeVar('_Mix_T')

    @exposed_directly
    def proxy_spawn(self: _Mix_T) -> _Mix_T:
        """
        spawn self in a new thread and return a proxy for self
        """
        if isinstance(getattr(self, 'proxy_resource', None), _ProxyServer):
            return self
        guard = self.proxy_spawn_guard()  # type: ignore
        if guard:
            raise ProxyError(guard)
        (self.proxy_q, self.proxy_cancel_flag), (q, cancel_flag) = _make_synchronization_objects()
        handler = _ProxyServer(self, q, cancel_flag)
        handler.start()
        atexit.register(self.proxy_join)  # type: ignore
        return self.__make_proxy(handler)  # type: ignore

    @exposed_directly
    def proxy_join(self: _Mix_T) -> _Mix_T:
        """
        kill proxy server and return original self
        """
        if not isinstance(getattr(self, 'resource', None), _ProxyServer):
            return self

        self.proxy_cancel_flag.set()
        self.proxy_q.kill_other()
        self.proxy_resource.join()
        self.proxy_cancel_flag.clear()
        resource = self.proxy_resource.resource
        atexit.unregister(resource.proxy_join)
        [delattr(self, attr) for attr in ('proxy_resource', 'proxy_cancel_flag', 'proxy_q')]
        return resource

    def proxy_check_cancelled(self) -> None:
        """
        should be used in long-running tasks
        """
        if hasattr(self, 'proxy_cancel_flag') and self.proxy_cancel_flag.is_set():
            raise CancelledError()

    def proxy_spawn_guard(self) -> str:
        """
        use this to prevent spawning if necessary setup work hasn't been done
        return truthy string to raise ProxyError(<returned string>)
        """
