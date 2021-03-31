"""
Usage:
    class MixinClass(register_on_init.Logged):
        @register.before('__init__')
        def method1(self) -> None: ...
        @register.before('__init__')
        def method2(self, init_arg) -> None: ...
        @register.after('__init__')
        def method3(self) -> None: ...

    class Example(MixinClass):
        def __init__(self, init_arg): ...

    class ExampleTerminal(Example):
        pass

    instance = ExampleTerminal('blah')
        > method1 executed
        > method2 executed with 'blah' passed
        > __init__ executed with 'blah' passed
        > method3 executed

register functions to execute before or after terminal class's method
functions are registered only on subclasses of Mixin
registered functions may accept either the args passed to terminal method or no args
note: if decorators and descriptors are mixed, stuff will fail silently and unavoidably
"""

from collections import defaultdict
from functools import wraps
from typing import Callable
from typing import Dict
from typing import Iterable
from typing import Set
from typing import TypeVar

__all__ = [
    'before',
    'after',
    'Mixin',
]

_function_registry_key = '_function_registry_dict_'
_class_registry_key = '_class_registry_dict_'
_unwrapped_method_key = '_original_method_key_'
_before_key = '__before__'
_after_key = '__after__'

_T = TypeVar('_T', bound=Callable)
_DECO_T = str
_METHOD_RUN_T = Iterable[str]


def _register(f: _T, order_key: str, wrapped_method: _DECO_T) -> _T:
    if not isinstance(wrapped_method, str):
        raise TypeError('must specify method for which to register decorated method')

    if f.__name__.startswith('__'):
        raise TypeError('cannot register a class private method (starts with __)')

    if not hasattr(f, _function_registry_key):
        setattr(f, _function_registry_key, defaultdict(set))

    getattr(f, _function_registry_key)[order_key].add(wrapped_method)
    return f


def before(method: _DECO_T) -> Callable[[_T], _T]:
    """see module documentation"""

    def inner(f: _T) -> _T:
        return _register(f, _before_key, method)

    return inner


def after(method: _DECO_T) -> Callable[[_T], _T]:
    """see module documentation"""

    def inner(f: _T) -> _T:
        return _register(f, _after_key, method)

    return inner


def _get_from_registry(cls: type):
    cls_method_registry = defaultdict(lambda: defaultdict(set))

    for cla in reversed(cls.__mro__[:-1]):

        existing = getattr(cla, _class_registry_key, None)
        if isinstance(existing, defaultdict):
            for wrapped_method, method_d in existing.items():
                for order_key, registered_fs in method_d.items():
                    for registered_f in registered_fs:
                        cls_method_registry[wrapped_method][order_key].add(registered_f)

        else:
            for name, f in cla.__dict__.items():
                method_d = getattr(f, _function_registry_key, None)
                if isinstance(method_d, dict):
                    for order_key, wrapped_methods in method_d.items():
                        for wrapped_method in wrapped_methods:
                            cls_method_registry[wrapped_method][order_key].add(name)

    getattr(cls, _class_registry_key, cls_method_registry)
    return cls_method_registry


def _perform(method_names: _METHOD_RUN_T, instance, *args, **kwargs) -> None:
    for method in method_names:
        _bound = getattr(instance, method).__get__(instance, type(instance))
        try:
            _bound(*args, **kwargs)
        except TypeError:
            _bound()


def _wrapper_factory(method_to_be_wrapped: Callable, wrapped_method_d: Dict[str, Set[str]]):
    @wraps(method_to_be_wrapped)
    def _wrapper(self, *args, **kwargs) -> None:
        _perform(wrapped_method_d[_before_key], self, *args, **kwargs)

        # SUPPRESS-LINTER <will throw TypeError if args are passed to placeholder>
        # noinspection PyArgumentList
        method_to_be_wrapped(self, *args, **kwargs)

        _perform(wrapped_method_d[_after_key], self, *args, **kwargs)

    setattr(_wrapper, _unwrapped_method_key, method_to_be_wrapped)
    return _wrapper


def _wrap_methods_with_registered_functions(cls: type) -> None:
    for wrapped_method_name, registered_d in _get_from_registry(cls).items():
        to_be_wrapped = getattr(cls, wrapped_method_name, None)

        if to_be_wrapped is None:
            def _to_be_wrapped(self) -> None:
                f"""placeholder method for {cls.__name__}"""

            to_be_wrapped = _to_be_wrapped

        else:
            to_be_wrapped = getattr(to_be_wrapped, _unwrapped_method_key, to_be_wrapped)

        setattr(cls, wrapped_method_name, _wrapper_factory(to_be_wrapped, registered_d))


class Mixin:
    """see module documentation"""

    def __init_subclass__(cls) -> None:
        _wrap_methods_with_registered_functions(cls)
        super().__init_subclass__()
