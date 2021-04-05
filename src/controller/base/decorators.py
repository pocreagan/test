import re
from collections import defaultdict
from enum import auto
from enum import Enum
from typing import *

from src.base.general import setdefault_attr_from_factory
from src.base.general import setdefault_attr_from_mro_or_factory
from src.controller.base.enums import SubscribeTo

__all__ = [
    'scan_method',
    'subscribe',
    'SubscribeTo',
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
    def __init__(self, f: _T, *message_types: Type, target: SubscribeTo = None) -> None:
        self._f = f
        self._message_types = message_types
        self._target = target

    def __set_name__(self, owner, name):
        for message_type in self._message_types:
            setdefault_attr_from_factory(
                owner, _subscribed_methods_key, lambda : defaultdict(dict)
            )[self._target][message_type] = self._f.__name__
        self._name = name

    def __get__(self, instance, owner) -> _T:
        self._f = self._f.__get__(instance, owner)
        setattr(owner, self._name, self._f)
        return self._f


def subscribe(*cla: Type, target: SubscribeTo = SubscribeTo.VIEW) -> Callable[[_T], _Subscribed[_T]]:
    def inner(f: _T) -> _Subscribed[_T]:
        return _Subscribed(f, *cla, target=target)

    return inner
