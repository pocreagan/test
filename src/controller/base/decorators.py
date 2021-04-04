import re
from typing import *

from src.base.general import setdefault_attr_from_mro_or_factory

__all__ = [
    'scan_method',
    'subscribe',
]

_T = TypeVar('_T', bound=Callable)
_DT = TypeVar('_DT', bound=type)

_scan_methods_key = 'scan_methods'


class _ScanMethod(Generic[_T]):
    def __init__(self, f: _T, pattern: re.Pattern) -> None:
        self._f = f
        self._pattern = pattern

    def __set_name__(self, owner, name):
        setdefault_attr_from_mro_or_factory(
            owner, _scan_methods_key, list
        ).append((name, self._pattern))
        setattr(owner, name, self._f.__get__(owner))

    def __get__(self, instance, owner) -> _T:
        pass


def scan_method(pattern: re.Pattern) -> Callable[[_T], _ScanMethod[_T]]:
    def inner(f: _T) -> _ScanMethod[_T]:
        return _ScanMethod(f, pattern)

    return inner


_subscribed_methods_key = 'subscribed_methods'


class _Subscribed(Generic[_T]):
    def __init__(self, f: _T, message_type: Type) -> None:
        self._f = f
        self._message_type = message_type

    def __set_name__(self, owner, name):
        setdefault_attr_from_mro_or_factory(
            owner, _subscribed_methods_key, dict
        )[self._message_type] = self._f.__name__
        setattr(owner, name, self._f.__get__(owner))

    def __get__(self, instance, owner) -> _T:
        pass


def subscribe(cla: Type) -> Callable[[_T], _Subscribed[_T]]:
    def inner(f: _T) -> _Subscribed[_T]:
        return _Subscribed(f, cla)

    return inner
