from typing import *

from src.base.general import setdefault_attr_from_factory

__all__ = [
    'subscribe',
]

_T = TypeVar('_T', bound=Callable)
_subscribed_methods_key = 'subscribed_methods'


class _Subscribed(Generic[_T]):
    def __init__(self, f: _T, *message_types: Type) -> None:
        self._f = f
        self._message_types = message_types

    def __set_name__(self, owner, name):
        for message_type in self._message_types:
            setdefault_attr_from_factory(
                owner, _subscribed_methods_key, dict
            )[message_type] = self._f.__name__
        self._name = name

    def __get__(self, instance, owner) -> _T:
        self._f = self._f.__get__(instance, owner)
        setattr(owner, self._name, self._f)
        return self._f


def subscribe(*cla: Type) -> Callable[[_T], _Subscribed[_T]]:
    def inner(f: _T) -> _Subscribed[_T]:
        return _Subscribed(f, *cla)

    return inner
