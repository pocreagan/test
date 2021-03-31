import warnings
from dataclasses import dataclass
from functools import wraps
from inspect import signature
from itertools import count
from operator import attrgetter
from time import perf_counter
from time import time
from typing import Any
from typing import Callable
from typing import Dict
from typing import Optional
from typing import Tuple
from typing import Type
from typing import TypeVar
from typing import Union

from src.base.general import setdefault_attr_from_factory

__all__ = [
    'with_method_done',
    'class_property',
    'cached_property',
    'multiple_dispatch',
    'bool_raises',
    'check_for_required_attrs',
    'configure_class',
    'raise_if',
    'suppress',
    'until_true_or_timeout',
    'not_implemented_warning',
]

PROPERTY_METHOD_T = Callable[[Any], Any]


_TC = TypeVar('_TC', bound=Callable)


def with_method_done(method_name: str):
    def outer(f: _TC) -> _TC:
        @wraps(f)
        def inner(self, *args, **kwargs):
            getattr(self, method_name)()
            return f(self, *args, **kwargs)

        return inner  # type: ignore

    return outer

class CustomDescriptor:
    def __init__(self, f: PROPERTY_METHOD_T) -> None:
        self._f = f
        self._cache_name = f'_{f.__name__}_cached_value'

    def __get__(self, instance, cls):
        raise NotImplementedError

    def _perform(self, obj):
        try:
            return self._f(obj)

        except Exception as e:
            raise AttributeError(f'failed to compute {type(self)}') from e


# noinspection PyPep8Naming
class class_property(CustomDescriptor):
    """
    @class_property | @class_property.cached
    cannot be used with .setter
    ! take care with subclassing
    TODO: needs more testing
    """

    def __init__(self, f: PROPERTY_METHOD_T, cached: bool = False) -> None:
        CustomDescriptor.__init__(self, f)
        self._cached = cached

    def __get__(self, _, cls) -> Any:
        if not all([self._cached, hasattr(cls, self._cache_name)]):
            value = self._perform(cls)
            if self._cached:
                setattr(cls, self._cache_name, value)

            return value

        return getattr(cls, self._cache_name)

    @classmethod
    def cached(cls, f: PROPERTY_METHOD_T) -> 'class_property':
        return cls(f, cached=True)


# noinspection PyPep8Naming
class cached_property(CustomDescriptor):
    """
    @cached_property
    stands in for functools.cached_property from later py versions
    """

    def __get__(self, instance, _):
        value = self._perform(instance)
        setattr(instance, self._f.__name__, value)
        return value


_T = TypeVar('_T')


def bool_raises(
        *exceptions: Optional[Type[Exception]]
) -> Callable[[Callable[[_T], Any]], Callable[[_T], bool]]:
    """
    returns True if e is raised by f else False
    e is suppressed, other exceptions are not caught
    if e is None, returns True if nothing is raised else False
    """

    def outer(f: Callable[[_T], Any]) -> Callable[[_T], bool]:

        @wraps(f)
        def inner(*args, **kwargs) -> bool:
            try:
                f(*args, **kwargs)

            except Exception as raised:
                if exceptions is None:
                    return False

                if isinstance(raised, exceptions):  # type: ignore
                    return True

                raise raised

            else:
                return exceptions is None

        return inner

    return outer


# noinspection PyPep8Naming
class check_for_required_attrs:
    """
    raises TypeError if ::required_attrs:: aren't (present on an object and of the right types)

    let _reqs = dict(attr1=int, attr2=(bool, None), ...)

    to verify that required class attributes have been declared:

        @check_for_required_attrs.declared_on_class(**_reqs)
        def __init__(...): ...

    to verify that required self attributes have been set:

        def method(self): ...
            check_for_required_attrs.set_on_instance(self, _reqs)
    """

    sentinel = object()

    @classmethod
    def __check(cls, o, required_attrs: Dict[str, Union[type, Tuple[type, ...]]]) -> None:
        o_t = type(o)
        for symbol, attr_t in required_attrs.items():
            value = getattr(o_t, symbol, cls.sentinel)
            if value is cls.sentinel or not isinstance(value, attr_t):
                raise TypeError(f'{o_t} must specify {symbol}: {attr_t}')

    @classmethod
    def declared_on_class(cls, **required_attrs: Union[type, Tuple[type, ...]]) -> Callable:

        def outer(f: Callable) -> Callable:
            @wraps(f)
            def inner(self, *args, **kwargs):
                cls.__check(self, required_attrs)
                return f(self, *args, **kwargs)

            return inner

        return outer

    @classmethod
    def set_on_instance(cls, instance, **required_attrs: Union[type, Tuple[type, ...]]) -> None:
        cls.__check(instance, required_attrs)


class _MultiMethod(object):
    """
    used by @multiple_dispatch
    """

    def __init__(self) -> None:
        self.type_map = {}
        self.default_implementation = None

    def __call__(self, *args):
        """
        tuple dict lookup, fallback: default_implementation
        """
        types = tuple(arg.__class__ for arg in args[1:])
        return self.type_map.get(types, self.default_implementation)(*args)

    @staticmethod
    def get_types(f: Callable) -> Tuple[Type]:
        """
        pulls parameter types from annotations and guards for non-type instances e.g. from typing
        """
        params = tuple(signature(f).parameters.values())[1:]

        # SUPPRESS-LINTER <i'm guarding against non-type return in the for loop>
        # noinspection PyTypeChecker
        args: Tuple[Type] = tuple(map(attrgetter('annotation'), params))
        for cla in args:
            if not isinstance(cla, type):
                raise TypeError('arg annotations must be types')
        return args

    def register(self, f: Callable) -> '_MultiMethod':
        if self.default_implementation is None:
            self.default_implementation = f
            wraps(f)(self)
        else:
            types = self.get_types(f)
            if types in self.type_map:
                raise TypeError("duplicate registration")
            self.type_map[types] = f
        return self


# SUPPRESS-LINTER <to conform to standard library pattern>
# noinspection SpellCheckingInspection
def multiple_dispatch(f: Callable) -> Callable:
    """
    the first func of name <name> to be decorated with this is registered as the default implementation
    any others are registered by non-bound parameter annotations, which must each be a type
    should not be used with keyword arguments
    raises TypeError on bad usage
    ex:
        class Blah:
            @multiple_dispatch
            def blah(self, *args): ... <- default implementation (annotations disregarded)
            @multiple_dispatch
            def blah(self, x: int y: list): ... <- specific implementation
            @multiple_dispatch
            def blah(self, x: int y: List[str]): ... <- fails at class declaration time
    """
    return setdefault_attr_from_factory(
        multiple_dispatch, '__registry', dict
    ).setdefault((getattr(f, '__module__'), f.__qualname__), _MultiMethod()).register(f)


def configure_class(error_on_overwrite: bool = False, **kwargs) -> Callable[[_T], _T]:
    """
    @configure_class(attrA=1, attrB=2)
    class Class: ...
     - or -
    self = configure_class(attrA=1, attrB=2)(Class)()

    useful when inheritance causes difficulty with passing args to Class.__init__()
    """

    def inner(cls: _T) -> _T:
        for k, v in kwargs.items():
            if error_on_overwrite and hasattr(cls, k):
                raise AttributeError(f'class configuration failed: "{k}" already set.')

            try:
                setattr(cls, k, v)

            except (AttributeError, TypeError, ValueError) as e:
                print(f'FAILED TO SET {k}={v} on {cls})')
                print(e)

        return cls

    return inner


def raise_if(raise_error: Optional[Type[Exception]]):
    """
    decorator factory.

    ex 1:
        suppress = raise_if(None)
        suppress(AttributeError)(lambda : raise AttributeError)()       <--- error is squashed
        suppress(AttributeError)(lambda : raise TypeError)()            <--- raises TypeError

    ex 2:
        raise_fatal_if = raise_if(FatalError)
        raise_fatal_if(AttributeError)(lambda : raise AttributeError)() <--- raises FatalError
        raise_fatal_if(AttributeError)(lambda : raise TypeError)()      <--- raises TypeError

    """

    @wraps(raise_if)
    def deco(*handled_exceptions: Type[Exception]):
        def outer(f: Callable[..., Any]) -> Callable[..., Any]:
            @wraps(f)
            def inner(*args, **kwargs):
                try:
                    return f(*args, **kwargs)

                except handled_exceptions as caught:
                    if raise_error:
                        raise raise_error from caught

            return inner

        return outer

    return deco


suppress = raise_if(None)


@dataclass
class _Result:
    """
    returned from until_true_or_timeout, below
    """
    last_result: bool = False
    was_timeout_reached: bool = True
    te: float = 0
    num_iterations: int = 0


def until_true_or_timeout(timeout: float) -> Callable[[Callable[..., bool]], Callable[..., _Result]]:
    """
    ex:
        def method(self) -> bool: ...

        __return_value: _Result = until_true_or_timeout(1.)(method)()
        last_result, was_timeout_reached = __return_value
    """

    def outer(f: Callable[..., bool]) -> Callable[..., _Result]:

        @wraps(f)
        def inner(*args, **kwargs) -> _Result:
            result = _Result()

            tf = time() + timeout
            for i in count(1):
                result.te = tf - time()
                if result.te > timeout:
                    break

                result.last_result = f(*args, **kwargs)
                result.num_iterations = i

                if result.last_result:
                    result.was_timeout_reached = False
                    break

            return result

        return inner

    return outer


def time_actor_method(f: Callable) -> Callable:
    """
    can only be called on an Actor's self method
    if the method is @exposed, this should be below that decorator
    """

    @wraps(f)
    def inner(self, *args, **kwargs):
        ti = perf_counter()
        r = f(self, *args, **kwargs)
        tf = perf_counter()

        try:
            self.info(f'{f.__qualname__}() took {(tf - ti) * 1000:03.1f}ms')

        except AttributeError:
            pass

        return r

    return inner


def not_implemented_warning(f: _T) -> _T:
    """
    returning NotImplementedError marks a method as an abstract method if method's owner is inherited
    even in a terminal class it actually raises the error
    this emits a warning instead, allowing execution to continue
    """

    @wraps(f)
    def inner(*args, **kwargs):
        warnings.warn(f'{f.__name__} not implemented yet', RuntimeWarning)
        return f(*args, **kwargs)

    return inner
