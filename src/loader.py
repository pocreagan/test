import ctypes
import tkinter as tk
from functools import partial
from multiprocessing import Process
from queue import Empty
from queue import Queue
from tkinter import font

import PIL.Image
import PIL.ImageTk
import win32api

from framework.model import logger, APP

log = logger(__name__)

__all__ = [
    'loader',
]


def _loader(q: Queue):
    """
    declare, init, and run loader window to allow time for
    heavy plt startup, xls parsing, db connection, etc
    """
    black = '#000000'
    white = '#ffffff'
    log_h = 100
    logo_fp = APP.R.img('wet_logo.png')
    log_font_size = 9

    class Screen:
        """
        uses win32 api to get active screen dimensions in pixels and inches, w/h ratio, dpi
        only works on windows
        """
        _MM_TO_IN = 0.0393700787

        def __init__(self, window: tk.Tk) -> None:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            self.resolution_w, self.resolution_h = [win32api.GetSystemMetrics(i) for i in [0, 1]]
            dc = ctypes.windll.user32.GetDC(window.winfo_id())
            self.width, self.height = [ctypes.windll.gdi32.GetDeviceCaps(dc, v) * self._MM_TO_IN for v in
                                       [4, 6]]
            self.w_h_ratio, self.dpi = self.width / self.height, int(self.resolution_w / self.width)
            log.debug(f'measured {repr(self)}')

        def __repr__(self) -> str:
            inches = f'{round(self.width, 2)}x{round(self.height, 2)}in'
            return f'Screen({self.resolution_w}x{self.resolution_h}px {self.dpi}dpi {inches})'

    class Logo(tk.Label):
        def __init__(self, parent, image) -> None:
            kwargs = dict(bg=black, anchor='n', image=image)
            super().__init__(parent, **kwargs)
            self.pack(fill=tk.BOTH, expand=1)

    class LogField(tk.Text):
        _max_length = 6

        @staticmethod
        def truncate(line: str, limit: int) -> str:
            """
            if a string is longer than limit, return a substring from start-limit
            """
            if len(line) > limit:
                return line[:limit]
            return line

        def add_line(self, line: str) -> None:
            self['state'] = 'normal'
            if self._length == self._max_length:
                self.delete(1.0, 2.0)
                self._length -= 1
            if self.index('end-1c') != '1.0':
                self.insert('end', '\n')
            self.insert('end', self._truncate(line))
            self._length += 1
            self['state'] = 'disabled'

        def __init__(self, parent: 'Loader', w: int) -> None:
            self._length = 0

            self.font = font.nametofont('TkFixedFont')
            self.font.config(size=log_font_size)
            limit = int(w / self.font.measure('m')) - 1
            self._truncate = partial(self.truncate, limit=limit)

            super().__init__(parent, state='disabled', wrap='none', relief='flat', cursor='arrow',
                             fg=white, bg=black, selectbackground=black, width=w,
                             inactiveselectbackground=black, font=self.font, height=log_h)
            self.pack(fill=tk.BOTH, expand=1)

    class Loader(tk.Tk):
        # ? https://stackoverflow.com/a/16115616

        def quit(self) -> None:
            if self.poll_after:
                self.after_cancel(self.poll_after)

            super().quit()

        def __post_init__(self) -> None:
            self.screen = Screen(self)
            self._logo_img = PIL.ImageTk.PhotoImage(self._logo_img)

            s_w, s_h = self.screen.resolution_w, self.screen.resolution_h
            w, h = int(self._logo_img.width()), int(self._logo_img.height())
            x_off, y_off = int((s_w // 2) - (w // 2)), int((s_h // 2) - ((h + log_h) // 2))
            self.geometry(f'{w}x{h + log_h}+{x_off}+{y_off}')

            self.logo = Logo(self, self._logo_img)
            self.log = LogField(self, w)

            self.poll_after = self.after(100, self.poll)
            log.info('started polling')

            self.mainloop()

        def __init__(self, _q: Queue) -> None:
            self.q = _q
            self._logo_img = PIL.Image.open(logo_fp)

            super().__init__()
            self.protocol('WM_DELETE_WINDOW', self.quit)
            self.attributes('-topmost', True)
            self.overrideredirect(True)

            self.__post_init__()

        def poll(self) -> None:
            while 1:
                try:
                    msg = self.q.get()

                except Empty:
                    break

                else:
                    self.log.add_line(msg)
                    if msg == '$STOP_LOADER$':
                        return self.quit()

    Loader(q)


def loader(q):
    p = Process(name='LOAD', target=_loader, args=(q,))
    p.start()
    return p
