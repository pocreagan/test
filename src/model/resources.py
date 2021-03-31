"""
application-wide repo
"""
# ? REQUIRE <C:\Projects\test_framework\src\framework\model\resources\yml>
# ? REQUIRE <C:\Projects\test_framework\src\framework\model\resources\font>
# ? REQUIRE <C:\Projects\test_framework\src\framework\model\resources\img>
# ? REQUIRE <C:\Projects\test_framework\src\framework\model\resources\dta>
# ? REQUIRE <C:\Projects\test_framework\src\framework\model\resources\dll>
import ctypes
import re
import subprocess
import sys
from functools import partial
from pathlib import Path
from socket import gethostname
from typing import *

from framework.base.load import *
from framework.base.log import logger
from framework.model.enums import Station

__all__ = [
    'APP',
    'logger',
]

log = logger(__name__)

DIR = Callable[..., Path]


class Resource:
    dta: DIR
    fake_data: DIR
    ini: DIR
    img: DIR
    light_meter_dll: DIR
    misc: DIR
    xlsx: DIR

    def __init__(self):
        # noinspection SpellCheckingInspection
        _root_path = getattr(sys, '_MEIPASS', None)
        self.is_binary = _root_path is not None
        if self.is_binary:
            _root_path = Path(_root_path)
        else:
            _root_path = Path(__file__).parent.parent
        self._root_path = str(_root_path / 'resources')
        font_number_re = re.compile(r'(\d{3})')
        self._fonts = {int(font_number_re.findall(f.name)[0]): f for f in self('font').iterdir()}
        self._resource_dirs = {'dta', 'fake_data', 'yml', 'img', 'dll', 'misc', 'xlsx', }

    def __call__(self, *args) -> Path:
        return Path(self._root_path, *args)

    def font(self, num: int) -> Path:
        return self._fonts[num]

    def __getattr__(self, k: str) -> DIR:
        if k in self._resource_dirs:
            setattr(self, k, partial(Path, self._root_path, k))
        return object.__getattribute__(self, k)


# noinspection PyPep8Naming
class View(Accessor):
    _values_d: dict
    __colors = None
    __fontsize = None

    class FontSize(Accessor):
        def _to_final(self, v: int) -> int:
            return int(v * self._multiplier)

    class Category(Accessor):
        def _to_final(self, v: tuple[int, ...]) -> str:
            return tuple_to_hex_color(v)

    class Colors(Accessor):
        _values_d: Dict[str, Dict[str, Tuple[int, ...]]]

        def _to_final(self, v):
            return View.Category(v)

    @property
    @lazy_access
    def COLORS(self) -> 'View.Colors':
        return self.Colors(self._view['colors'])

    @property
    @lazy_access
    def FONTSIZE(self) -> 'View.FontSize':
        return self.FontSize(self._view['font_size'],
                             _multiplier=self._view['FONT_SIZE_MULTIPLIER'])

    def __init__(self, app) -> None:
        self.APP = app
        self._view = self.APP.get.yml('view')
        super().__init__(self._view)


class _Get:
    def outer(self, f: Callable[[Path], Any]):
        ext = f.__name__
        d: Path = self.APP.R(f.__name__)

        def inner(filename: str):
            fp = d / f'{filename}.{ext}'
            try:
                return_value = f(fp)
            except Exception as e:
                log.error(f'failed to load {fp.name}', stack_info=True)
                raise e
            else:
                log.info(f'successfully loaded {fp.name}')
                return return_value

        return inner

    def __getattr__(self, k: str) -> Callable[[Path], Any]:
        f: Callable[[Path], Any] = getattr(Get, k, None)
        if callable(f):
            setattr(self, k, self.outer(f))
        return object.__getattribute__(self, k)

    def __init__(self, app: 'App') -> None:
        self.APP = app


# noinspection PyPep8Naming
class App:
    __View = View
    _v_display_cats = ["major", "minor", "micro"]

    @property
    @lazy_access
    def last_commit(self) -> str:
        return subprocess.run('git rev-parse HEAD', capture_output=True).stdout.strip().decode()

    @property
    @lazy_access
    def LIGHT_METER_DLL(self) -> ctypes.CDLL:
        return self.get.dll('mkusb')  # type: ignore

    @property
    @lazy_access
    def BUILD(self) -> Accessor:
        """
        information from the last binary build
        """
        return self.get.yml('build')  # type: ignore

    @property
    @lazy_access
    def INSTRUMENTS(self) -> Accessor:
        """
        instrument constants from ini
        """
        return Accessor(self.get.yml('instruments'))  # type: ignore

    @property
    @lazy_access
    def DATABASE(self) -> Accessor:
        """
        database constants from ini
        """
        return Accessor(self.get.yml('db'))  # type: ignore

    @property
    @lazy_access
    def V(self) -> View:
        """
        view constants from ini
        """
        return self.__View(self)

    @property
    @lazy_access
    def G(self) -> Accessor:
        """
        general constants from ini
        """
        return Accessor(self.get.yml('general'))  # type: ignore

    @property
    @lazy_access
    def STATION(self) -> Station:
        # noinspection PyUnusedLocal
        hostname = gethostname().lower()
        override_hostname = r'tm-lview1'
        if hostname != override_hostname:
            log.warning(f'STATION hostname {hostname} overridden with {override_hostname}')
            hostname = override_hostname
        station_info = self.G.stations.get(hostname, 'pcreagan-laptop')
        category, enum, resolution = [station_info[k] for k in ['category', 'enum', 'resolution']]
        station = Station[enum]
        human = self.G.tests[category][enum]['human_readable']
        setattr(station, 'category', category)
        setattr(station, 'import_path', (category, station.name))
        setattr(station, 'resolution', resolution)
        setattr(station, 'hostname', hostname)
        setattr(station, 'human_readable', human)
        setattr(station, 'instruments', self.G.tests[category][enum]['instruments'])
        setattr(station, 'scan_parsers', self.G.tests[category][enum]['scan_parsers'])
        setattr(station, 'combined_string', f'{hostname} [{human}]')
        return station

    @property
    @lazy_access
    def TITLE(self) -> str:
        return f'{self.G.APPLICATION_NAME} v{self.BUILD["v"]} [ {self.STATION.hostname} ]'

    @property
    @lazy_access
    def IS_PRODUCTION(self) -> bool:
        return (self.BUILD['build_type'] == 'Production') and self.IS_BINARY

    @property
    @lazy_access
    def FREEZE(self) -> str:
        return '\n'.join((self.TITLE,
                          f'build_id: {self.BUILD["build_id"]} build_type: {self.BUILD_TYPE}',
                          f'last_commit: {self.last_commit}'))

    @property
    @lazy_access
    def BUILD_TYPE(self) -> str:
        if self.IS_BINARY:
            return self.BUILD['build_type'] + ' binary'
        else:
            _display_version = [str(getattr(self.PY, k)) for k in self._v_display_cats]
            return f'interpreter v{".".join(_display_version)}'

    @property
    @lazy_access
    def PY(self) -> tuple:
        """
        python interpreter version from sys
        """
        return sys.version_info

    def log_runtime_info(self):
        if self.IS_BINARY:
            log.debug(f'build_id: {self.BUILD["build_id"]} build_type: {self.BUILD_TYPE}')
            log.debug(f'last_commit: {self.last_commit}')
        else:
            # noinspection PyUnresolvedReferences
            if APP.PY.major != self.PY[0] or self.PY.minor != self.PY[1]:
                log.error(f'{self.G.APPLICATION_NAME} requires Python v{self.PY}')
                exit()

    def __init__(self):
        # binary bootloader creates a temp folder and stores path in sys
        self.R = Resource()
        self.IS_BINARY = self.R.is_binary
        log.debug(f'APP.R path: "{self.R()}"')
        self.get = _Get(self)


APP = App()
