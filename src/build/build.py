from pathlib import Path
from typing import *

from make.build_specification import *

__DEBUG__ = True


class Testing(BuildSpecification):
    # APPLICATION SETTINGS
    APPLICATION_ENTRY_POINT: str = 'testing'
    PROJECT_PATH: Path = Path(r'C:\Projects\jose')
    RESOURCE_DIR: Path = PROJECT_PATH / r'src\model'
    BUILD_YAML: Path = RESOURCE_DIR / r'resources\yml\build.yml'
    ICON_PATH: Optional[Path] = RESOURCE_DIR / r'resources\img\wet_logo.ico'
    ADDITIONAL_BINARIES = []

    # MAKE SETTINGS
    SPEC_PATH: Optional[Path] = None
    DO_CLEAN: bool = True
    ENCRYPT_BYTECODE: bool = False
    UPX_COMPRESS: bool = False
    ONE_FILE: bool = True
    ASK_PERMISSION: bool = False
    # noinspection SpellCheckingInspection
    UPX_EXCLUDE = ['vcruntime140.dll']

    # APPLICATION DEBUG
    KEEP_CONSOLE: bool = True

    # PYINSTALLER DEBUG
    LOG_LEVEL: Optional[BuildSpecification.LOG] = None
    PRINT_BOOTLOADER_PROGRESS: bool = False
    PRINT_IMPORT_PROGRESS: bool = False
    DISCRETE_FROZEN_SOURCE_FILES: bool = False

    # PYINSTALLER FIXES
    HOOKS = None
    HIDDEN_IMPORTS = None
    EXCLUDED_MODULES = None


class Instruments(Testing):
    APPLICATION_ENTRY_POINT = 'instruments'


class Production(Testing):
    KEEP_CONSOLE: bool = False


if __name__ == '__main__':
    BuildSpecification.make(Testing if __DEBUG__ else Production)
    # BuildSpecification.make(Instruments)
