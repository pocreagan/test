import ctypes
import tempfile
import tkinter
from pathlib import Path
from tkinter.font import Font
from typing import *

import win32api
from fontTools import ttLib

from framework.base.load import lazy_access
from framework.model import *

__all__ = [
    'Screen',
    'TypeFace',
    'Icon',
]

log = logger(__name__)


class Screen:
    """
    uses win32 api to get active screen dimensions in pixels and inches, w/h ratio, dpi
    only works on windows
    """
    _MM_TO_IN = 0.0393700787

    def __init__(self, window: tkinter.Tk) -> None:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        self.resolution_w, self.resolution_h = [win32api.GetSystemMetrics(i) for i in [0, 1]]
        dc = ctypes.windll.user32.GetDC(window.winfo_id())
        self.width, self.height = [ctypes.windll.gdi32.GetDeviceCaps(dc, v) * self._MM_TO_IN for v in [4, 6]]
        self.w_h_ratio, self.dpi = self.width / self.height, int(self.resolution_w / self.width)
        log.debug(f'measured {repr(self)}')

    def __repr__(self) -> str:
        inches = f'{round(self.width, 2)}x{round(self.height, 2)}in'
        return f'Screen({self.resolution_w}x{self.resolution_h}px {self.dpi}dpi {inches})'


class TypeFace:
    """
    allows non-system-standard fonts to be used in Tk widgets
    grabs name and family name from ttf file
    exposes Tk font instance with tk_font property
    only works on windows
    """
    _FONT_SPECIFIER_NAME_ID = 4
    _FONT_SPECIFIER_FAMILY_ID = 1
    _lookup = {'name': _FONT_SPECIFIER_NAME_ID,
               'family': _FONT_SPECIFIER_FAMILY_ID}

    _encodings = {True: 'utf-16-be',
                  False: 'latin-1'}

    _FR_NOT_ENUM = 0x20
    _FR_PRIVATE = 0x10
    _flags = {(False, False): _FR_NOT_ENUM,
              (True, False): _FR_PRIVATE | _FR_NOT_ENUM,
              (False, True): 0,
              (True, True): _FR_PRIVATE}

    _added_fonts: Set[str] = set()

    name: str = None
    family: str = None

    @classmethod
    def get_names(cls, fp: Union[Path, str]) -> Tuple[str, ...]:
        """
        refactored a gist for speed and brevity
        """
        # ? https://gist.github.com/pklaus/dce37521579513c574d0
        d = {r.nameID: r.string for r in ttLib.TTFont(str(fp))['name'].names}
        name, family = [d[i].decode(cls._encodings[b'\x00' in d[i]]) for k, i in cls._lookup.items()]
        return name, family

    @classmethod
    def load(cls, name: str, fp: str, is_private: bool, is_enumerable: bool) -> bool:
        """
        add a non-system-standard font for access by the python interpreter
        needed for linotype typefaces
        """
        if name not in cls._added_fonts:
            if ctypes.windll.gdi32.AddFontResourceExW(
                    ctypes.byref(ctypes.create_unicode_buffer(fp)),
                    cls._flags[(is_private, is_enumerable)], 0):
                cls._added_fonts.add(name)
            else:
                return False
        return True

    @property
    @lazy_access
    def tk_font(self) -> Font:
        return Font(family=self.name)

    def __init__(self, fp: Union[Path, str], is_private: bool = True, is_enumerable: bool = True):
        self.is_private, self.is_enumerable, self.fp = is_private, is_enumerable, str(fp)
        self.name, self.family = self.get_names(self.fp)
        self.load(self.name, self.fp, self.is_private, self.is_enumerable)
        log.debug(f'loaded {repr(self)}')

    def __repr__(self) -> str:
        return f'TypeFace("{self.name}")'


class Icon:
    @staticmethod
    def make_temporary_transparent_icon() -> str:
        """
        save temporary icon to temp file and return file path to it
        """
        icon_path = tempfile.mkstemp()[1]
        with open(icon_path, 'wb') as f:
            f.write((b'\x00\x00\x01\x00\x01\x00\x10\x10\x00\x00\x01\x00\x08\x00h\x05\x00\x00'
                     b'\x16\x00\x00\x00(\x00\x00\x00\x10\x00\x00\x00 \x00\x00\x00\x01\x00'
                     b'\x08\x00\x00\x00\x00\x00@\x05\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                     b'\x00\x01\x00\x00\x00\x01') + b'\x00' * 1282 + b'\xff' * 64)
        log.debug(f'made temporary transparent window icon')
        return icon_path
