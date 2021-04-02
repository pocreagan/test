import ctypes
import tkinter

import win32api

from src.base.log import logger

__all__ = [
    'Screen',
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
