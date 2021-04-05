import dataclasses
import functools
import multiprocessing
import multiprocessing.connection
import queue
import threading
from time import sleep
from time import time
from typing import Any
from typing import Callable
from typing import cast
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
from typing import Type
from typing import TypeVar
from typing import Union

from stringcase import snakecase

from src.base.concurrency.message import *
from src.base.general import surrender_thread_control
from src.base.log import logger

__all__ = [
    'ProcessConnection',
    'ThreadConnection',
    'SentinelReceived',
    'ConnectionClosed',
    'SYNC_COMM_ERROR_T',
    'CallbackRegistry',
    'Thread',
    'ThreadHandler',
    'Process',
    'parent_terminus',
    'ChildTerminus',
    'make_duplex_connection',
]

log = logger(__name__)

ENDPOINT = Union[multiprocessing.connection.Connection, queue.Queue]


class SentinelReceived(Exception):
    pass


class ConnectionClosed(Exception):
    pass


SYNC_COMM_ERROR_T = SentinelReceived, ConnectionClosed

PIPE_EXCEPTIONS = BrokenPipeError, EOFError, OSError

CONN = Union['ProcessConnection', 'ThreadConnection']
CONN_T = Type[CONN]


class Connection:
    _sentinel = '$Connection._sentinel:END$'
    _start_message = '$Connection._sentinel:START$'

    def __init__(self, tx: ENDPOINT, rx: ENDPOINT) -> None:
        self.tx, self.rx = tx, rx

    def kill_other(self) -> None:
        try:
            self.put_sentinel()
            self.get()
        except SentinelReceived:
            pass

    def _is_sentinel(self, msg) -> bool:
        return self._sentinel == msg

    def _raise_if_sentinel(self, msg) -> None:
        if self._is_sentinel(msg):
            raise SentinelReceived

    def put_started(self) -> None:
        try:
            self.put(self._start_message)
        except ConnectionClosed:
            pass

    def put_sentinel(self) -> None:
        try:
            self.put(self._sentinel)
        except ConnectionClosed:
            pass

    def put(self, msg) -> None:
        raise NotImplementedError

    def poll(self) -> bool:
        raise NotImplementedError

    def task_done(self) -> None:
        raise NotImplementedError

    def get(self):
        raise NotImplementedError

    def get_nowait(self):
        raise NotImplementedError

    def __iter__(self):
        return self

    def __next__(self):
        try:
            return self.get_nowait()
        except queue.Empty:
            raise StopIteration

    @property
    def all(self):
        """
        return all messages currently in rx queue
        """
        msgs = [msg for msg in self]
        if msgs:
            return msgs
        raise queue.Empty


class ThreadConnection(Connection):
    tx: queue.Queue
    rx: queue.Queue

    def put(self, msg) -> None:
        return self.tx.put(msg)

    def poll(self) -> bool:
        return not self.rx.empty()

    def task_done(self) -> None:
        return self.rx.task_done()

    def get_nowait(self):
        return self.get(0.)

    def get(self, timeout: Optional[float] = None):
        msg = self.rx.get(timeout=timeout)
        self._raise_if_sentinel(msg)
        return msg


class ProcessConnection(Connection):
    tx: multiprocessing.connection.Connection
    rx: multiprocessing.connection.Connection

    def put(self, msg) -> None:
        try:
            return self.tx.send(msg)
        except PIPE_EXCEPTIONS as e:
            raise ConnectionClosed from e

    def poll(self) -> bool:
        try:
            return self.rx.poll()
        except PIPE_EXCEPTIONS as e:
            raise ConnectionClosed from e

    def task_done(self):
        pass

    def get(self):
        try:
            msg = self.rx.recv()
            self._raise_if_sentinel(msg)
        except PIPE_EXCEPTIONS as e:
            raise ConnectionClosed from e
        else:
            return msg

    def get_nowait(self):
        if not self.poll():
            raise queue.Empty
        return self.get()


_ARG_T = TypeVar('_ARG_T', bound=ENDPOINT)
_T = TypeVar('_T', bound=CONN)


def make_duplex_connection(cla: Type[_T], tx1: _ARG_T, rx1: _ARG_T,
                           tx2: _ARG_T, rx2: _ARG_T) -> Tuple[_T, _T]:
    return cla(tx1, rx1), cla(tx2, rx2)


class MessageHandler:
    """
    wrapper around an obj
    exports the q duplex comm channel, which should be the only resource to the obj
    """
    _poll_parent: Optional[Callable[[], None]] = None

    _implements: Union[multiprocessing.Process, threading.Thread]
    _poll_delay_s: float = 0.
    _get_blocking: bool = True

    @dataclasses.dataclass
    class Task:
        task: Callable
        args: tuple
        kwargs: Dict[str, Any]
        execute_at: float

        def perform(self):
            return self.task(*self.args, **self.kwargs)

    @staticmethod
    def _task_sorter(task: 'MessageHandler.Task') -> float:
        """
        used in .schedule to sort ._scheduled_tasks by execution time
        """
        return task.execute_at

    def schedule(self, t: float, task: Callable, *args, **kwargs) -> None:
        """
        schedule actions for next time queue is empty
        task to be performed in t seconds with args, kwargs
        enforces ascending order by t
        can extend to add priority and absolute ordering
        """
        was_task = bool(self._scheduled_tasks)
        new_task = self.Task(task, args, kwargs, time() + t)
        self._scheduled_tasks.append(new_task)
        if was_task:
            if self._scheduled_tasks[-2].execute_at > new_task.execute_at:
                self._scheduled_tasks.sort(key=self._task_sorter)

    def pick_scheduled_task(self):
        """
        can extend to add priority and absolute ordering
        """
        if time() > self._scheduled_tasks[0].execute_at:
            task, *self._scheduled_tasks = self._scheduled_tasks
            return task

    def perform_one_scheduled_task(self) -> bool:
        """
        get earliest scheduled task and execute it if it's time to do so
        enqueues Message.Notification if any
        return whether a task has been performed
        """
        if self._scheduled_tasks:

            task = self.pick_scheduled_task()
            if task:
                task.perform()
                return True

        return False

    def _poll_delay(self) -> None:
        """
        called when no request and no scheduled task
        override to give children processing time
        """
        sleep(cast(float, self._poll_delay_s))

    def __init__(self, actor=None, name: str = None, log_name: str = None) -> None:
        assert self._implements
        if actor:
            self.actor = actor.inject(self)
            name = self.actor.name
            self.log = logger(self.actor.log_name)

        else:
            assert name
            assert log_name
            self.log = logger(log_name)

        self._scheduled_tasks: List['MessageHandler.Task'] = []
        self._q, self.q = self._make_duplex_channel()
        self._registered_messages = CallbackRegistry()

        if self._poll_delay_s == 0.:
            self._poll_delay = surrender_thread_control  # type: ignore

        self.poll_parent = self._poll_blocking if self._poll_blocking else self._poll_non_blocking

        # noinspection PyTypeChecker
        self._implements.__init__(self, target=self.main, name=name, daemon=True)  # type: ignore

    def notify(self, msg: Message.Notification) -> None:
        """
        used to send a message outside the request-response loop
        """
        self._q.put(msg)

    def dispatch(self, msg) -> None:
        """
        handle message received from the controller
        """
        self.handle_message(msg)
        self._q.task_done()

    def _prioritize(self, messages):
        """
        can be extended for prioritized handling
        """
        _ = self
        return messages

    def _poll_non_blocking(self) -> None:
        """
        core of the Actor's operation
        dequeue Message self from controller
        __perform_task a scheduled task if no queued commands
        """
        try:
            list(map(self.dispatch, self._prioritize(self._q.all)))

        except queue.Empty:
            if not self.perform_one_scheduled_task():
                self._poll_delay()

    @functools.wraps(_poll_non_blocking)
    def _poll_blocking(self) -> None:
        self.dispatch(self._q.get())

    def poll(self) -> None:
        self.poll_parent()

    def mainloop(self) -> None:
        while 1:
            self.poll()

    def main(self) -> None:
        """
        this is called when .start() is called in controller
        loops until controller sends stop message
        sends stopped message when it ends
        """
        self.log.info('STARTING...')
        self.__post_init__()
        self.log.info('STARTED')

        try:
            self.mainloop()

        except SentinelReceived:
            self.on_sentinel_received()

        except ConnectionClosed:
            self.on_connection_closed()

        except KeyboardInterrupt:
            pass

        finally:
            self.on_shutdown()
            self.log.info('STOPPED')
            self._q.put_sentinel()

    @staticmethod
    def _make_duplex_channel() -> Tuple[CONN, CONN]:
        """
        called on __init__ to expose a duplex message channel
        """
        raise NotImplementedError

    def __post_init__(self):
        self._q.put_started()

    def handle_message(self, msg) -> None:
        self.log.instrument_debug(f'-> {msg}')
        self.handle(msg)

    def handle(self, msg) -> None:
        """
        do something with received message
        test equipment example:
            response = self.obj.dispatch(msg)
            self.q.task_done()
            self.q.put(response)
        """
        raise NotImplementedError

    def on_sentinel_received(self) -> None:
        """
        override hook
        """

    def on_connection_closed(self) -> None:
        """
        override hook
        """

    def on_shutdown(self):
        """
        override hook
        """


CALLBACK = Callable[..., None]


class CallbackRegistry(dict):
    __lock = None

    @property
    def _lock(self) -> threading.RLock:
        """
        locks can't be pickled, so one is created on first call
        """
        if self.__lock is None:
            self.__lock = threading.RLock()
        return self.__lock

    def __setitem__(self, msg: Message.ResponseRequired, callback: CALLBACK = None) -> None:
        if callback:
            with self._lock:
                super().__setitem__(msg.id, callback)

    def __getitem__(self, msg: Message.ResponseRequired) -> Optional[CALLBACK]:
        with self._lock:
            return super().get(msg.id, None)

    def __delitem__(self, msg: Message.ResponseRequired) -> None:
        with self._lock:
            try:
                super().__delitem__(msg.id)
            except KeyError:
                pass

    def __call__(self, msg: Message.ResponseRequired) -> None:
        """
        get, remove, and perform callback if one has been registered
        """
        with self._lock:
            callback = self[msg]
            del self[msg]

        if callback:
            callback(msg)


class Thread(threading.Thread, MessageHandler):
    _implements = threading.Thread
    _get_blocking = True

    @staticmethod
    def _make_duplex_channel() -> Tuple[CONN, CONN]:
        q1, q2 = queue.Queue(), queue.Queue()
        return make_duplex_connection(ThreadConnection, q1, q2, q2, q1)

    def handle(self, msg) -> None:
        self._q.put(self.actor.dispatch(msg))

    def __init__(self, **kwargs) -> None:
        MessageHandler.__init__(self, **kwargs)


class ThreadHandler:
    thread_classes: Dict[str, Type[Thread]]

    def __post_init__(self, *args) -> None:
        _ = args
        self._registered_messages = CallbackRegistry()
        self.threads = {k: Thread(actor=cla()) for k, cla in self.thread_classes.items()}
        [self.threads[k].start() for k in self.thread_classes.keys()]
        [t.q.get() for t in self.threads.values()]

    def handle_child_message(self, msg: Message.ResponseRequired) -> None:
        (log.info if msg.is_success else log.warning)(f'<- {msg}')
        self._registered_messages(msg)

    def poll_thread(self, thread: Thread) -> None:
        try:
            self.handle_child_message(thread.q.get_nowait())
        except queue.Empty:
            pass
        else:
            thread.q.task_done()

    def poll(self):
        list(map(self.poll_thread, self.threads.values()))

    def perform_thread_action(self, name: str, msg, callback: Callable = None, **kwargs) -> None:
        self.threads[name].q.put(msg)
        if kwargs:
            callback = functools.partial(callback, **kwargs)  # type: ignore
        self._registered_messages[msg] = callback
        log.instrument_debug(f'-> {msg}')

    def close(self) -> None:
        [t.q.put_sentinel() for t in self.threads.values()]
        [t.join(timeout=.05) for t in self.threads.values()]


class Process(multiprocessing.Process, MessageHandler):
    _implements = multiprocessing.Process
    _get_blocking = False

    @staticmethod
    def _make_duplex_channel():
        (rx1, tx1), (rx2, tx2) = multiprocessing.Pipe(False), multiprocessing.Pipe(False)
        return make_duplex_connection(ProcessConnection, tx1, rx2, tx2, rx1)

    def handle(self, msg) -> None:
        pass

    def __init__(self, log_q: multiprocessing.Queue, **kwargs):
        self._log_q = log_q
        MessageHandler.__init__(self, **kwargs)


class ParentTerminus:
    SELF_ACTION = LayeredAction
    OTHER_ACTION = LayeredAction

    _q: ProcessConnection
    _registered_messages: CallbackRegistry

    def _perform_other_action(self, o, f: str, *args, callback: Callable = None, **kwargs) -> None:
        """
        __build request message
        register callback if any
        enqueue message
        """
        msg = self.OTHER_ACTION(o, f, *args, **kwargs)
        self._registered_messages[msg] = callback
        self._q.put(msg)

    @functools.lru_cache()
    def make_self_component_name(self, name: str) -> Optional[str]:
        """
        make attr name from __class__.__name__ of counterpart widget
        """
        for k in [name, name.lower(), snakecase(name)]:
            if hasattr(self, k):
                return k
        return None

    def _perform_self_action(self, o, msg: LayeredAction) -> None:
        """
        __perform_task self action on object<o>
        enqueue msg marked for success
        """
        method = getattr(o, msg.f, None)
        if method:
            try:
                response = method(*msg.args, **msg.kwargs)

            except Exception as e:
                return self._q.put(msg.exception(e))

            else:
                if response is None:
                    return self._q.put(msg.success())

                elif response:
                    return self._q.put(response)

        return self._q.put(msg.failure())

    def perform_self_action(self, msg: LayeredAction) -> None:
        """
        determine what to do with self request from other
        if method is not defined as specified in message, fails request and returns it
        """
        if msg.o is None:
            self._perform_self_action(self, msg)

        else:
            o = self.make_self_component_name(msg.o)
            if o:
                self._perform_self_action(getattr(self, o), msg)

            else:
                self._q.put(msg.failure())

    def handle_message(self, msg) -> None:
        """
        __perform_task one action on self if appropriate
        if message has been registered for a callback on __complete, __perform_task callback
        if message comes in an unexpected format, log warning
        """
        if isinstance(msg, self.SELF_ACTION):
            self.perform_self_action(msg)

        elif isinstance(msg, self.OTHER_ACTION):
            self._registered_messages(msg)

        else:
            log.warning(f'NOT HANDLED -> {msg}')


def parent_terminus(self: Type[LayeredAction], other: Type[LayeredAction]) -> Type[ParentTerminus]:
    """
    class factory to set self and other actions on declare-time
    """

    class _ParentTerminus(ParentTerminus):
        SELF_ACTION = self
        OTHER_ACTION = other

    return _ParentTerminus


class ChildTerminus:
    parent: ParentTerminus

    def _perform_other_action(self, o, f: str, *args, callback: Callable = None, **kwargs):
        o_ = self.__class__.__name__ if o is self else o
        # noinspection PyProtectedMember
        return self.parent._perform_other_action(o_, f, *args, **dict(**kwargs, callback=callback))

    def parent_widget(self, cls, *, fail_silently: bool = False):
        try:
            return getattr(self.parent, cls.__name__.lower())
        except AttributeError:
            if not fail_silently:
                raise
