import functools
import os
import random
import time
from enum import Enum
from pathlib import Path
from time import perf_counter
from time import sleep
from typing import Union
from typing import Any
from typing import Callable
from typing import Dict
from typing import Iterable
from typing import Optional
from typing import TypeVar

__all__ = [
    'EqEnum',
    'Wait',
    'do_if_not_done',
    'do_nothing',
    'safe_calc',
    'surrender_thread_control',
    'chain',
    'truncate',
    'call',
    'timer',
    'bound_float_on_range',
    'random_condition',
    'setdefault_attr',
    'setdefault_attr_from_factory',
    'time_func',
    'text_patrick',
    'test_nom_tol',
    'dict_from',
    'set_from',
    'WorkingDirectory',
]


_T = TypeVar('_T')


class WorkingDirectory:
    def __init__(self, dir_: Union[Path, str]) -> None:
        self._dir = dir_

    def __enter__(self) -> None:
        self._prev = os.getcwd()
        os.chdir(self._dir)

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        os.chdir(self._prev)


def dict_from(obj, keys: Iterable[str]) -> Dict[str, Any]:
    return {k: getattr(obj, k) for k in keys}


def set_from(src, dst: _T, keys: Iterable[str]) -> _T:
    [setattr(dst, k, getattr(src, k)) for k in keys]
    return dst


class EqEnum(Enum):
    """
    use in place of enum.Enum to allow imported object equality checks
    """

    def __hash__(self):
        """
        used to enable sqlalchemy to use instances as a Column
        """
        return hash(self.name)

    def __eq__(self, other):
        """
        necessary because local instances are different objects to ones created on first import
            profiled faster than one-liner and type(obj).__name__
        """
        try:
            if self.__class__.__name__ == other.__class__.__name__:
                return self.value == other.value
        except AttributeError:
            pass
        return False


class Wait:
    """
    ex:
    with Wait(5.) as wait:
        if not do_something():
            wait.cancel()
    """
    _delay_f: Callable = sleep
    _time_f: Callable = perf_counter

    @staticmethod
    def _round_up_ms(v: float) -> float:
        return round(v + .0005, 3)

    @staticmethod
    def _clamp_non_neg(v: float) -> float:
        return max(0., v)

    def __init__(self, length: float, ti: float = None) -> None:
        self.do, self.ti, self.end = True, ti, length

    def __enter__(self) -> 'Wait':
        self.end += self.ti or self._time_f()
        return self

    @property
    def time_remaining(self) -> float:
        return self.end - self._time_f()

    def cancel(self) -> None:
        self.do = False

    def __exit__(self, _type, value, traceback) -> None:
        if _type is None and self.do:
            self._delay_f(self._clamp_non_neg(self._round_up_ms(self.time_remaining)))


def safe_calc(f: Callable) -> Callable:
    """
    __perform_task arithmetic with x/0 handled by returning None
    """

    @functools.wraps(f)
    def inner(*args, **kwargs) -> Optional[float]:
        try:
            return f(*args, **kwargs)
        except ZeroDivisionError:
            return

    return inner


def do_if_not_done(action_name: str, is_do: bool, attr_name: str = None) -> Callable:
    """
    if is_do: do something if not done
    else: undo something if done
    state is stored in new attr _{action_name}
    """
    action_name = f'_{action_name}' if attr_name is None else attr_name

    def outer(f: Callable) -> Callable:
        @functools.wraps(f)
        def inner(self, *args, **kwargs) -> None:
            if is_do ^ getattr(self, action_name, False):
                f(self, *args, **kwargs)
                setattr(self, action_name, is_do)

        return inner

    return outer


def do_nothing(*args, **kwargs) -> None:
    """
    placeholder for unset callbacks
    """
    _, _ = args, kwargs


def surrender_thread_control(*args, **kwargs) -> None:
    _, _ = args, kwargs
    sleep(0.)


def chain(f: Callable):
    """
    return self or cls
    """

    @functools.wraps(f)
    def inner(self, *args, **kwargs):
        f(self, *args, **kwargs)
        return self

    return inner


def truncate(line: str, limit: int) -> str:
    """
    if a command_string is longer than limit, return a substring from start-limit
    """
    if len(line) > limit:
        return line[:limit]
    return line


def call(_object, method_name: str, *args, **kwargs) -> None:
    """
    if method exists on object, calls it with args and kwargs
    """
    f = getattr(_object, method_name, None)
    if f:
        f(*args, **kwargs)


def timer(f: Callable):
    @functools.wraps(f)
    def inner(*args, **kwargs):
        ti = time.perf_counter()
        f(*args, **kwargs)
        tf = time.perf_counter()
        print(f.__name__, ':', tf - ti, 'seconds')

    return inner


def bound_float_on_range(num: float, lower: float, higher: float) -> float:
    """
    clamp num on range [lower, higher]
    """
    return max(lower, min(higher, num))


def random_condition(chance: float = None):
    chance = .5 if chance is None else chance
    return random.random() < chance


# * this works but i don't want to initialize colorama on every import of this module
# class ClearLine:
#     _initialized = False
#
#     def __init__(self):
#         import os
#         import subprocess
#         import colorama
#
#         if not self.__class__._initialized:
#             subprocess.call('', shell=True)
#             colorama.init()
#             colorama.deinit()
#             self.__class__._initialized = True
#
#         self.get_terminal_size = os.get_terminal_size
#         for i in range(3):
#             try:
#                 _ = self.get_terminal_size(i)
#                 self.index = i
#                 break
#             except OSError:
#                 continue
#
#     def __call__(self, n: int = 1):
#         _, columns = self.get_terminal_size(self.index)
#         [print('\u001b[2A\n' + (' ' * columns), end='\r') for _ in range(n)]
#
#
# clear_line = ClearLine()


def time_func(f, *args, num=1, **kwargs) -> None:
    from statistics import mean

    def do() -> float:
        ti = perf_counter()
        f(*args, **kwargs)
        return perf_counter() - ti

    times = [do() for _ in range(num)]

    print('\n------------------')
    print(f.__name__, args, kwargs)
    print(max(times), 'max')
    print(min(times), 'min')
    print(mean(times), 'mean')
    print('------------------\n')


_T = TypeVar('_T')


# SUPPRESS-LINTER <to conform to builtin func names>
# noinspection SpellCheckingInspection
def setdefault_attr(o: object, k: str, v: _T) -> _T:
    if not hasattr(o, k):
        setattr(o, k, v)
    return getattr(o, k)


# SUPPRESS-LINTER <to conform to builtin func names>
# noinspection SpellCheckingInspection
def setdefault_attr_from_factory(o: object, k: str, factory: Callable[[], _T]) -> _T:
    if not hasattr(o, k):
        setattr(o, k, factory())
    return getattr(o, k)


def text_patrick(message: str):
    from smtplib import SMTP

    email = 'wetmessagingpcreagan@gmail.com'
    server = SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(email, 'wet_messaging69')
    server.sendmail(email, f'562-284-8437@messaging.sprintpcs.com', message)


def test_nom_tol(nom: float, tol: float, result: float) -> bool:
    return (nom - tol) <= result <= (nom + tol)
