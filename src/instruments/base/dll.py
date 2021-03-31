import os
from ctypes import CDLL
from functools import partial
from pathlib import Path
from typing import Any
from typing import Callable
from typing import List
from typing import Tuple

__all__ = [
    'DLLFunc',
    'load_dll',
]


def load_dll(fp: Path) -> CDLL:
    _prev = os.getcwd()
    try:
        os.chdir(fp.parent)
        return CDLL(str(fp))
    finally:
        os.chdir(_prev)


class DLLFunc:
    """
    convenience wrapper around ctypes functionality
    """

    def __init__(self, f: Callable, return_type: type = None, arg_types: List[type] = None,
                 args: Tuple = None) -> None:
        self.name = self.__name__ = f.__name__
        self._buffer = None
        if return_type:
            f.restype = return_type
        if arg_types:
            # noinspection SpellCheckingInspection
            f.argtypes = arg_types
        if args:
            f = partial(f, *args)
        self._f = f

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return self._f(*args, **kwargs)
