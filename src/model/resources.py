"""
application-wide repo
"""
# ? REQUIRE <C:\Projects\test\resources\cfg>
# ? REQUIRE <C:\Projects\test\resources\font>
# ? REQUIRE <C:\Projects\test\resources\img>

import re
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from socket import gethostname
from typing import *

import yaml as yml

from src.base.log import logger
from src.model import configuration
from src.model.enums import Station
from src.model.load import *

__all__ = [
    'APP',
    'RESOURCE',
    'COLORS',
    'logger',
]


class _Resource:
    def __init__(self):
        # noinspection SpellCheckingInspection
        _root_path = getattr(sys, '_MEIPASS', None)
        self.is_binary = _root_path is not None
        if self.is_binary:
            _root_path = Path(_root_path)
        else:
            _root_path = Path(__file__).parent.parent.parent
        self._root_path = str(_root_path / 'resources')
        self._fonts = {
            int(re.findall(r'-(\d{3})', f.name)[0]): f for f in self('font').iterdir()
        }

    def __call__(self, *args) -> Path:
        return Path(self._root_path, *args)

    def font(self, num: int) -> Path:
        return self._fonts[num]

    def img(self, name: str) -> Path:
        return self('img', name)

    def yml(self, name: str) -> Path:
        return self('cfg', f'{name}.yml')

    @lru_cache(maxsize=None)
    def cfg(self, name: str) -> Dict[str, Any]:
        with open(self.yml(name)) as rf:
            return yml.load(rf, Loader=yml.FullLoader)


RESOURCE = _Resource()


class _Colors:
    config_obj = configuration.from_resource(RESOURCE.yml('view'), header='colors')
    light_grey = config_obj.tk_color()
    medium_grey = config_obj.tk_color()
    dark_grey = config_obj.tk_color()
    black = config_obj.tk_color()
    white = config_obj.tk_color()
    green = config_obj.tk_color()
    orange = config_obj.tk_color()
    red = config_obj.tk_color()
    blue = config_obj.tk_color()
    lime = config_obj.tk_color()


COLORS = _Colors()
COLORS.config_obj.update_from_file_system()


class _Station:
    def __init__(self):
        # noinspection PyUnusedLocal
        hostname = gethostname().lower()
        # noinspection SpellCheckingInspection
        hostname = r'tm-lview2'
        station_info = RESOURCE.cfg('general').get('stations').get(hostname, 'pcreagan-laptop')
        category, enum, resolution = [station_info[k] for k in ['category', 'enum', 'resolution']]
        station = Station[enum]
        _from_enum = RESOURCE.cfg('general').get('tests')[category][enum]
        human = _from_enum['human_readable']
        self.category = category
        self.import_path = ('src', 'stations', category, station.name)
        self.resolution = resolution
        self.hostname = hostname
        self.human_readable = human
        self.instruments = _from_enum['instruments']
        self.scan_parsers = _from_enum['scan_parsers']
        self.combined_string = f'{hostname} [{human}]'


# noinspection PyPep8Naming
class App:
    __v_display_cats = ["major", "minor", "micro"]

    @lazy_access
    def last_commit(self) -> str:
        if self.IS_BINARY:
            return self.BUILD['last_commit']
        return subprocess.run('git rev-parse HEAD', capture_output=True).stdout.strip().decode()

    @lazy_access
    def BUILD(self) -> Dict:
        """
        information from the last binary build
        """
        return RESOURCE.cfg('build')

    @lazy_access
    def DATABASE(self) -> Dict:
        """
        database constants from ini
        """
        return RESOURCE.cfg('db')

    @lazy_access
    def G(self) -> Dict:
        """
        general constants from ini
        """
        return RESOURCE.cfg('general')


    @lazy_access
    def V(self) -> Dict:
        """
        general constants from ini
        """
        return RESOURCE.cfg('view')

    @lazy_access
    def STATION(self) -> _Station:
        return _Station()

    @lazy_access
    def TITLE(self) -> str:
        return f'{self.name} v{self.BUILD["v"]} [ {self.STATION.hostname} ]'

    @lazy_access
    def IS_PRODUCTION(self) -> bool:
        return (self.BUILD['build_type'] == 'Production') and self.IS_BINARY

    @lazy_access
    def FREEZE(self) -> str:
        return '\n'.join((self.TITLE,
                          f'build_id: {self.BUILD["build_id"]} build_type: {self.BUILD_TYPE}',
                          f'last_commit: {self.last_commit}'))

    @lazy_access
    def BUILD_TYPE(self) -> str:
        if self.IS_BINARY:
            return self.BUILD['build_type'] + ' binary'
        else:
            _display_version = [str(getattr(self.PY, k)) for k in self.__v_display_cats]
            return f'interpreter v{".".join(_display_version)}'

    @lazy_access
    def PY(self) -> tuple:
        """
        python interpreter version from sys
        """
        return sys.version_info

    def check_py_version(self) -> None:
        py_v = self.G.get('PYTHON_VERSION')
        # noinspection PyUnresolvedReferences
        if self.PY.major != py_v[0] or self.PY.minor != py_v[1]:
            print(f'{self.name} requires Python v{self.PY}')
            exit()

    def runtime_info(self) -> str:
        s = f'build_type: {self.BUILD_TYPE} last_commit: {self.last_commit}'
        if self.IS_BINARY:
            return s + f' build_id: {self.BUILD["build_id"]}'
        else:
            return f'build type: {self.BUILD_TYPE}'

    def __init__(self):
        self.name = self.G.get('APPLICATION_NAME')
        self.IS_BINARY = RESOURCE.is_binary


APP = App()
