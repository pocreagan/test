import json
import os
import re
import sys
from datetime import datetime
from enum import auto
from enum import Enum
from itertools import chain
from pathlib import Path
from time import time
from typing import *

import PyInstaller.__main__
import yaml as yml
from key_generator.key_generator import generate

__all__ = [
    'BuildSpecification',
]


class BuildSpecification:
    # ? https://pyinstaller.readthedocs.io/en/stable/usage.html#options
    # ? https://github.com/pyinstaller/pyinstaller/issues/2785

    class LOG(Enum):
        TRACE = auto()
        DEBUG = auto()
        INFO = auto()
        WARN = auto()
        ERROR = auto()
        CRITICAL = auto()

    # APPLICATION SETTINGS
    APPLICATION_ENTRY_POINT: str = 'main'
    PROJECT_PATH: Path = None
    RESOURCE_DIR: Path = None
    ICON_PATH: Optional[Path] = None
    BUILD_YAML: Path = None
    ADDITIONAL_BINARIES: List[Path] = []

    # MAKE SETTINGS
    DO_CLEAN: bool = True
    ENCRYPT_BYTECODE: bool = True
    UPX_COMPRESS: bool = False
    UPX_EXCLUDE = None
    ONE_FILE: bool = True
    ASK_PERMISSION: bool = False

    # APPLICATION DEBUG
    KEEP_CONSOLE: bool = True

    # PYINSTALLER DEBUG
    LOG_LEVEL: Optional[LOG] = None
    PRINT_BOOTLOADER_PROGRESS: bool = False
    PRINT_IMPORT_PROGRESS: bool = False
    DISCRETE_FROZEN_SOURCE_FILES: bool = False

    # PYINSTALLER FIXES
    HOOKS: Dict[str, List[str]] = None
    HIDDEN_IMPORTS: List[str] = None
    EXCLUDED_MODULES: List[str] = None

    def make_resource_paths(self, v: Path) -> str:
        v = v.resolve().absolute()
        try:
            source = v.relative_to(self.SPEC_PATH)
            dest = v.relative_to(self.RESOURCE_DIR)
        except ValueError:
            s = 'FAILED TO INCLUDE %s: RESOURCES MUST BE CONTAINED IN %s'
            print(s % (v, self.RESOURCE_DIR))
            exit()
        else:
            if source.is_dir():
                return f'{source}' + r'\*;' + f'{dest}'
            return f'{source};{dest}'

    def _make_paths(self):
        self._APPLICATION_ENTRY_POINT = self.APPLICATION_ENTRY_POINT + '.py'
        self._PROJECT_PATH: Path = self.PROJECT_PATH
        self.SPEC_PATH: Path = self._PROJECT_PATH / 'src'
        build_path = self._PROJECT_PATH / 'build'
        self.DESTINATION_PATH: Path = build_path / 'bin'
        self.WORKING_PATH: Path = build_path / 'dat'
        self._HOOKS_DIR: Path = self.WORKING_PATH / 'hooks'
        self.BINARY_PATH: Path = self.DESTINATION_PATH / (self.APPLICATION_NAME + '.exe')

    def _make_debug(self):
        self._DEBUG: List[str] = []
        if self.PRINT_IMPORT_PROGRESS:
            self._DEBUG += ['imports']
        if self.PRINT_BOOTLOADER_PROGRESS:
            self._DEBUG += ['bootloader']
        if self.DISCRETE_FROZEN_SOURCE_FILES:
            # noinspection SpellCheckingInspection
            self._DEBUG += ['noarchive']

    def _make_key(self) -> None:
        self._KEY = None
        if self.ENCRYPT_BYTECODE:
            self._KEY = generate(1, '', 16, 16, type_of_value='char', capital='mix',
                                 extras=list(map(str, range(10))), seed=round(time())).get_key()

    def _make_log(self):
        if self.LOG_LEVEL:
            assert isinstance(self.LOG_LEVEL, self.LOG)
            self._LOG_LEVEL = self.LOG_LEVEL.name
        else:
            self._LOG_LEVEL = None

    def _make_require(self) -> bool:
        python_file = re.compile(r'.py$')
        require_regex = re.compile(r'# \? REQUIRE <(.+)>')

        self._ADDITIONAL_FILES_OR_DIRS, is_good = [], True
        for directory, _, files in os.walk(str(self.SPEC_PATH)):
            for file_name in files:
                path = Path(directory, file_name)
                full_path = str(path)
                if python_file.search(file_name):
                    with open(full_path, 'r') as f:
                        for match in require_regex.findall(f.read()):
                            required_file = match
                            required_path = Path(required_file)
                            is_present = required_path.exists()
                            is_good &= is_present
                            print(f'{path.relative_to(self.SPEC_PATH)} REQUIRES',
                                  f'{required_path.relative_to(self.SPEC_PATH)} ->',
                                  'PRESENT' if is_present else 'ABSENT')
                            self._ADDITIONAL_FILES_OR_DIRS.append(Path(required_file))

        return is_good

    def _make_includes(self):
        self.__ADDITIONAL_FILES_OR_DIRS: List[str] = list(
            map(self.make_resource_paths, self._ADDITIONAL_FILES_OR_DIRS))
        self._ADDITIONAL_BINARIES: List[str] = list(map(self.make_resource_paths, self.ADDITIONAL_BINARIES))

    def __init__(self):
        assert self.RESOURCE_DIR
        assert self.PROJECT_PATH
        assert self.BUILD_YAML
        self.APPLICATION_NAME = self.__class__.__name__

        self._make_paths()
        self._make_debug()
        self._make_key()
        self._make_log()
        if not self._make_require():
            print('NOT ALL REQUIRED FILES AND DIRS ARE PRESENT')
            exit()
        self._make_includes()

    @property
    def _required_args(self) -> List[str]:
        # noinspection SpellCheckingInspection
        return ['--name=%s' % self.APPLICATION_NAME,
                '--onefile' if self.ONE_FILE else '--onedir',
                '--noconfirm',
                r'--upx-dir=C:\upx_dir',
                '--distpath=%s' % self.DESTINATION_PATH,
                '--workpath=%s' % self.WORKING_PATH,
                '--console' if self.KEEP_CONSOLE else '--windowed', ]

    @staticmethod
    def _discretionary(k: str, v) -> List[str]:
        if isinstance(v, list):
            return [k % element for element in (v or [])]
        else:
            if v:
                if '%' in k:
                    return [k % v]
                return [k]
            return []

    @property
    def _discretionary_args(self) -> List[str]:
        # noinspection SpellCheckingInspection
        _DISCRETIONARY_ARGS = (('--clean', self.DO_CLEAN),
                               ('--specpath=%s', self.SPEC_PATH),
                               ('--log-level=%s', self._LOG_LEVEL),
                               ('--key=%s', self._KEY),
                               ('--icon=%s', self.ICON_PATH),
                               ('--debug=%s', self._DEBUG),
                               ('--add-data=%s', self.__ADDITIONAL_FILES_OR_DIRS),
                               ('--add-binary=%s', self._ADDITIONAL_BINARIES),
                               ('--hidden-import=%s', self.HIDDEN_IMPORTS),
                               ('--upx-exclude=%s', self.UPX_EXCLUDE),
                               ('--exclude-module=%s', self.EXCLUDED_MODULES),)
        return list(chain(*[self._discretionary(k, v) for k, v in _DISCRETIONARY_ARGS]))

    def args(self) -> List[str]:
        args = list(chain(self._required_args, self._discretionary_args))
        if self.HOOKS:
            args += ["--additional-hooks-dir=%s" % self._HOOKS_DIR]
        if not self.UPX_COMPRESS:
            args += [r'--noupx']
        args += [self._APPLICATION_ENTRY_POINT]
        return args

    def make_hooks(self):
        try:
            os.remove(self._HOOKS_DIR)
        except IOError:
            pass
        if self.HOOKS:
            os.makedirs(self._HOOKS_DIR, exist_ok=True)
            for explicit_import, implicit_imports in self.HOOKS.items():
                with open(str(self._HOOKS_DIR / explicit_import / '.py'), 'w+') as hook_file:
                    hook_file.write('')
                    # noinspection SpellCheckingInspection
                    hook_file.write(
                        'hiddenimports = [' + ','.join([f'"{imp}"' for imp in implicit_imports]) + ']')

    def cleanup_hooks(self):
        if self.HOOKS:
            os.remove(self._HOOKS_DIR)

    def cleanup_spec(self):
        try:
            spec_file_name = f'{self.APPLICATION_NAME}.spec'
            os.rename(self.SPEC_PATH / spec_file_name,
                      self.WORKING_PATH / self.APPLICATION_NAME / spec_file_name)
        except FileNotFoundError:
            pass

    def run_binary(self) -> None:
        os.system(f'"{self.BINARY_PATH}"')

    @classmethod
    def get_build(cls) -> dict:
        # noinspection PyUnresolvedReferences
        with open(cls.BUILD_YAML) as y:
            return yml.load(y, Loader=yml.FullLoader)

    @classmethod
    def update_build(cls, build: dict) -> None:
        # noinspection PyUnresolvedReferences
        with open(cls.BUILD_YAML, 'w') as y:
            yml.dump(build, y)

    @classmethod
    def update_build_version_number(cls, ) -> int:
        build = cls.get_build()
        build['build_id'] += 1
        cls.update_build(build)
        return build['build_id']

    @classmethod
    def update_build_name(cls, build_type: str) -> None:
        build = cls.get_build()
        build['build_type'] = build_type
        cls.update_build(build)

    @classmethod
    def _make(cls, version: int) -> None:
        max_python = (3, 10)
        if sys.version_info >= max_python:
            print('PYINSTALLER DOES NOT SUPPORT PYTHON VERSION >=%s.%s. ABORTING...' % max_python)
            exit()

        build_spec: BuildSpecification = cls()
        pyinstaller_args: List[str] = build_spec.args()
        print('PYINSTALLER ARGS -> ', json.dumps(pyinstaller_args, indent=4), '\n\n')

        if cls.ASK_PERMISSION:
            if input('BUILD EXE? (?i)[Y|N] -> ').upper() != 'Y':
                return print('\nDID NOT BUILD')

        build_spec.make_hooks()
        os.chdir(build_spec.SPEC_PATH)

        ti = datetime.now()
        build_spec.update_build_name(build_spec.APPLICATION_NAME)

        # noinspection PyBroadException
        try:
            PyInstaller.__main__.run(pyinstaller_args)

        except Exception as _:
            s = f'FAILED TO BUILD '

        else:
            s = f'SUCCESSFULLY BUILT v{version} '

        finally:
            build_spec.cleanup_hooks()
            build_spec.cleanup_spec()

        tf = datetime.now()
        seconds = (tf - ti).total_seconds()
        multiplier, string = {True: (1, 's'), False: (1000, 'ms')}[seconds > 1.]
        print('\n' + s + 'IN {t:.03f}{string}'.format(t=seconds * multiplier, string=string))

    @classmethod
    def make(cls, build) -> None:
        version = build.update_build_version_number()
        start_dir = os.getcwd()
        os.chdir(r'/')
        try:
            build._make(version)
        finally:
            os.chdir(start_dir)
