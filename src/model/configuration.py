import logging
import os
import threading
from functools import lru_cache
from operator import attrgetter
from pathlib import Path
from typing import Any
from typing import Callable
from typing import Dict
from typing import Generic
from typing import List
from typing import Optional
from typing import Type
from typing import TypeVar
from typing import Union

import yaml as yml

from src.base.general import setdefault_attr_from_factory
from src.model.load import tuple_to_hex_color

__all__ = [
    'Configuration',
    'get_configs_on_object',
    'update_configs_on_object',
]

_T = TypeVar('_T')
_PATH_T = Union[Path, str]

_no_default_sentinel = object()
_config_obj_dict_key = '_config_obj_dict_key_'
_config_fields_dict_key = '_config_fields_dict_key_'

_cached_yml = False
_config_file_root = Path(r'\\wet-pdm\Common\Test Data Backup\test\versioned')


def log_level(level: str) -> int:
    return getattr(logging, level.upper())


class _ConfigField(Generic[_T]):
    name: str

    def __init__(self, _t: _T, header: Optional[str], key: str = None, default=None,
                 guard: Callable[..., bool] = None, transform: Callable = None) -> None:
        self.key = key
        self._type = _t
        self.header = header
        self.guard = guard
        self.transform = transform
        self.default = default

    def _get_from_config(self, config, k: str):
        raise NotImplementedError

    def _narrow_lookup(self, config, header):
        raise NotImplementedError

    def _check_and_transform(self, k: str, v):
        if callable(self.transform):
            v = self.transform(v)
        # noinspection PyTypeHints
        if self._type and not isinstance(v, self._type):
            raise TypeError(f'configured field "{k}" must be one of {self._type}')
        if callable(self.guard) and not self.guard(v):
            raise ValueError(f'configured field "{k}" failed provided guard')
        return v

    def narrow_lookup(self, config: _T, header) -> _T:
        if header is not None:
            try:
                return self._narrow_lookup(config, header)
            except KeyError:
                raise ValueError(f'{type(self).__qualname__}: header "{header}" not found')
        return config

    def set_value(self, config) -> None:
        config = self.narrow_lookup(config, self.header)
        try:
            v = self._get_from_config(config, self.name)
        except Exception as e:
            if self.default is _no_default_sentinel:
                raise e
            v = self.default
        setattr(self.owner, self.name, self._check_and_transform(self.name, v))

    def __set_name__(self, owner, name: str):
        self.owner = owner
        self.name = name


class _ConfigFieldFromDict(_ConfigField):
    def _narrow_lookup(self, config: Dict[str, Any], header: Optional[str]) -> Dict[str, Any]:
        return config[header]

    def _get_from_config(self, config, k: str):
        try:
            if self.key is None or '.' not in self.key:
                return config[self.key or k]
            *first, last = self.key.split('.')
            for k in first:
                config = config[k]
            return config[last]
        except KeyError:
            raise AttributeError(f'failed to find config value "{self.key or k}')


class _ConfigFieldFromObj(_ConfigField):
    def _narrow_lookup(self, config: Dict[str, Any], header: Optional[str]) -> Dict[str, Any]:
        return getattr(config, header)

    def _get_from_config(self, config, k: str):
        try:
            return attrgetter(self.key or k)(config)
        except AttributeError:
            raise AttributeError(f'failed to find config value "{self.key or k}')


_shared_drive_checked = False


def _check_path(fp: _PATH_T) -> str:
    global _shared_drive_checked

    if not (os.path.exists(r'\\wet-pdm\Common') or _shared_drive_checked):
        raise ValueError('Must be connected to the W shared drive.')
    _shared_drive_checked = True

    fp = str(_config_file_root / fp)

    if isinstance(fp, str):
        if not os.path.isabs(fp):
            raise ValueError(f'{__name__} requires an abs path.')
    else:
        raise ValueError(f'{__name__} requires a str or Path arg')

    if not os.path.exists(fp):
        raise ValueError(f'{__name__}: no file found at {fp}')
    return fp


class _ConfigFrom:
    original_fp: str
    def __init__(self, fp: str, header: str, field_type: Type[_ConfigField]) -> None:
        self.fp = fp
        self.header = header
        self._field_type = field_type
        self._fields: List[_ConfigField] = []

    def field(self, _t: Type[_T], key: str = None, default: _T = None,
              guard: Callable[[_T], bool] = None, transform: Callable = None) -> _T:
        default = _no_default_sentinel if default is None else default  # type: ignore
        # noinspection PyTypeChecker
        field = self._field_type(_t, self.header, key=key,  # type: ignore
                                 guard=guard, transform=transform, default=default)  # type: ignore
        self._fields.append(field)
        return field

    def tk_color(self) -> str:
        # noinspection PyTypeChecker
        return self.field(str, transform=tuple_to_hex_color)

    def __set_name__(self, owner, name):
        self.owner = owner
        self.name = name
        setdefault_attr_from_factory(owner, _config_obj_dict_key, dict)[self.name] = self

    def update_from_file_system(self) -> None:
        self.update_from(_load_yml(self.fp))

    def update_from(self, config: Dict[str, Any]) -> None:
        [field.set_value(config) for field in self._fields]


class Configuration:
    # @classmethod
    # def from_dict(cls, d: Dict[str, Any], header: str = None, name: str = None) -> _ConfigFrom:
    #     return _ConfigFrom(cls.__narrow_lookup(d, header), _ConfigFieldFromDict, name)
    # @classmethod
    # def from_obj(cls, obj) -> _ConfigFrom:
    #     return _ConfigFrom(obj, _ConfigFieldFromObj, obj.__qualname__)
    pass


def update_configs_on_object(obj) -> None:
    [config.update_from_file_system() for config in get_configs_on_object(obj)]


def from_yml(fp: _PATH_T, header: str = None) -> _ConfigFrom:
    cfg = _ConfigFrom(_check_path(fp), header, _ConfigFieldFromDict)
    cfg.original_fp = fp
    return cfg


def from_resource(fp: _PATH_T, header: str = None) -> _ConfigFrom:
    cfg = _ConfigFrom(fp, header, _ConfigFieldFromDict)
    cfg.original_fp = fp
    return cfg


_lock = threading.RLock()


def _load_yml(fp: str) -> Dict:
    with _lock:
        with open(fp) as y:
            return yml.load(y, Loader=yml.FullLoader)


def get_configs_on_object(obj) -> List[_ConfigFrom]:
    return list(getattr(obj, _config_obj_dict_key, {}).values())


if _cached_yml:
    _load_yml = lru_cache(maxsize=None)(_load_yml)
