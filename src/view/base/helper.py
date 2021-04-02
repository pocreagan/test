import functools
from typing import *
from tkinter.filedialog import askopenfilename, asksaveasfilename
import dataclasses

__all__ = [
    'File',
    'with_enabled',
]


def with_enabled(widget):
    """
    enables a widget, performs method, and returns widget to previous state
    """

    def outer(f) -> Callable:
        @functools.wraps(f)
        def inner(*args, **kwargs) -> None:
            _prev_setting, widget['state'] = widget['state'], 'normal'
            try:
                f(*args, **kwargs)
            finally:
                widget['state'] = _prev_setting

        return inner

    return outer


class File:
    @dataclasses.dataclass
    class FileType:
        extension: str

        @property
        def tuple(self) -> Tuple[str, str]:
            return f'.{self.extension}', f'*.{self.extension}'

    XLS = FileType('xls')
    XLSX = FileType('xlsx')
    CSV = FileType('csv')
    ALL = FileType('*')

    @staticmethod
    def _get_file(f, title: str, directory: str, *file_types: 'File.FileType') -> str:
        return f(initialdir=directory,
                 title=title,
                 filetypes=tuple(ft.tuple for ft in file_types)).name

    @classmethod
    def open(cls, title: str, directory: str, *file_types) -> str:
        return cls._get_file(askopenfilename, title, directory, *file_types)

    @classmethod
    def save(cls, title: str, directory: str, *file_types) -> str:
        return cls._get_file(asksaveasfilename, title, directory, *file_types)
