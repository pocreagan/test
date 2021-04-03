import os
from ctypes import CDLL
from functools import wraps
from pathlib import Path
from types import ModuleType
from typing import Callable
from typing import Dict
from typing import Generic
from typing import Tuple
from typing import TypeVar
from typing import Union

import yaml as yml

__all__ = [
    'Accessor',
    'Get',
    'lazy_access',
    'dynamic_import',
    'tuple_to_hex_color',
]

PATH_LIKE = Union[Path, str]


class Accessor:
    def _to_final(self, v):
        _ = self
        return v

    def __init__(self, d: Dict, **kwargs) -> None:
        self._values_d = d
        [setattr(self, k, v) for k, v in kwargs.items()]

    def __getattr__(self, k: str) -> str:
        if k in self._values_d:
            setattr(self, k, self._to_final(self._values_d[k]))
        return object.__getattribute__(self, k)


class Get:
    @staticmethod
    def yml(fp: PATH_LIKE) -> dict:
        """
        loads a yml yml file's contents from the resources dir
        """
        with open(fp) as y:
            return yml.load(y, Loader=yml.FullLoader)

    @staticmethod
    def dll(fp: Path) -> CDLL:
        """
        CDLL constructor only works with the cwd set
        """
        os.add_dll_directory(str(fp.parent))
        return CDLL(fp.name)


def tuple_to_hex_color(color: Tuple[int, ...]) -> str:
    return "#%02x%02x%02x" % color[:3]


_lazy_access_sentinel = object()
_T = TypeVar('_T')


# noinspection PyPep8Naming
class lazy_access(Generic[_T]):
    def __init__(self, f: Callable[..., _T]) -> None:
        self._f = f

    def __get__(self, instance, owner) -> _T:
        v = self._f(instance)
        setattr(instance, self._f.__name__, v)
        return v

def dynamic_import(module: str, *path_parts):
    from importlib import import_module
    return import_module(f'.{module}', '.'.join(path_parts))


def import_from_path(qualified_name: str, fp: str) -> ModuleType:
    """
    imported module's __name__ is set to @qualified_name
    """
    from importlib.util import spec_from_file_location
    from importlib.util import module_from_spec

    spec = spec_from_file_location(qualified_name, fp)
    module = module_from_spec(spec)
    # noinspection PyUnresolvedReferences
    spec.loader.exec_module(module)
    return module
