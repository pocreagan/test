import tkinter as tk
from itertools import chain
from pathlib import Path
from typing import *

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
from matplotlib import cbook
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.image import FigureImage

from framework.model import logger
from framework.view.chart.helper import timer

log = logger(__name__)

__all__ = [
    'Root',
    'Region',
]

ANIMATED_ARTISTS = List[plt.Artist]
VARIABLE_OBJ = Union[plt.Artist, Iterable]
ITERATION_DATA = Any
PATH_LIKE = Union[str, Path]


class Widget:
    def __post_init__(self) -> None:
        pass

    def __init__(self) -> None:
        self.name = self.__class__.__name__
        self.children = list()
        self._variables = list()
        self.__animated = list()

    def var(self, obj: VARIABLE_OBJ) -> VARIABLE_OBJ:
        _var = self._variables.append
        if hasattr(obj, '__iter__'):
            [_var(o) for o in obj]
        else:
            _var(obj)
        return obj

    @property
    def animated(self) -> ANIMATED_ARTISTS:
        if not self.__animated:
            self.__animated = list(self._variables)
            self.__animated.extend(chain(*[c.animated for c in self.children]))
        return self.__animated

    def _propagate(self, f: str) -> None:
        """
        perform method on self, then on children
        then if <method>_after is defined, performs it
        """
        getattr(self, f'_{f}')()
        [getattr(child, f)() for child in self.children]
        if method := getattr(self, f'_{f}_after', None):
            method()

    def _set_background(self) -> None:
        raise NotImplementedError

    def _init_results(self) -> None:
        raise NotImplementedError

    def _reset_results(self) -> None:
        raise NotImplementedError

    def set_background(self) -> None:
        self._propagate('set_background')

    def init_results(self) -> None:
        self._propagate('init_results')

    def reset_results(self) -> None:
        self._propagate('reset_results')


class Root(Widget):
    tk_widget: Optional[tk.Frame]
    canvas: Optional[FigureCanvasTkAgg]
    background_img: Optional[FigureImage]

    def __init__(self, params: dict, w: int = 1429, h: int = 799,
                 dpi: int = 141, color: str = '#000000', **kwargs) -> None:
        Widget.__init__(self)

        self.params = params
        self.w = w
        self.h = h
        self.dpi = dpi
        self.face_color = color

        matplotlib.use("TkAgg")
        matplotlib.rcParams['toolbar'] = 'None'
        matplotlib.rcParams['font.family'] = 'Linotype Univers 430 Regular'

        self.fig: plt.Figure = plt.figure(
            figsize=(self.w / self.dpi, self.h / self.dpi),
            dpi=self.dpi, facecolor=self.face_color,
        )
        self.gs = self.fig.add_gridspec(nrows=90, ncols=160, left=0,
                                        right=1, top=1, bottom=0, hspace=0, wspace=0)

        self.properties = kwargs
        self.artists = {}
        self.tk_widget = None
        self.canvas = None
        self.background_img = None
        self._bg = None
        self._initialized = None

        self.__post_init__()

    def for_tk(self, parent: Union[tk.Tk, tk.Frame, tk.Canvas]) -> tk.Canvas:
        self.tk_widget = parent
        self.canvas = FigureCanvasTkAgg(self.fig, master=parent)
        widget = self.canvas.get_tk_widget()
        widget.pack(fill=tk.BOTH, expand=1)
        return widget

    @staticmethod
    def load_img(fp: PATH_LIKE) -> np.array:
        return plt.imread(cbook.get_sample_data(fp))

    @timer
    def save_img(self, fp: PATH_LIKE) -> None:
        self.fig.savefig(fp, transparent=True)

    @timer
    def set_background_from_img(self, img_array: np.array) -> None:
        self.background_img = plt.figimage(img_array)
        self.background_img.set_zorder(-999)

    def update(self, iteration_data: ITERATION_DATA) -> None:
        raise NotImplementedError

    def init(self) -> None:
        self._initialized = self._initialized or self.init_results() or True
        self.reset_results()
        self._bg = self._bg or self.canvas.copy_from_bbox(self.canvas.figure.bbox)

    def __call__(self, iteration_data: list[ITERATION_DATA]):
        list(map(self.update, iteration_data))
        self.canvas.restore_region(self._bg)
        list(map(self.canvas.figure.draw_artist, self.animated))
        self.canvas.blit(self.canvas.figure.bbox)

    def _set_background(self) -> None:
        pass

    def _init_results(self) -> None:
        pass

    def set_result(self, *args) -> None:
        pass

    def _reset_results(self) -> None:
        pass


class Region(Widget):
    def axis_manipulation(self) -> None:
        raise NotImplementedError

    def __init__(self, parent, axis: plt.Axes = None, **kwargs) -> None:
        Widget.__init__(self)

        self.parent = parent
        self.parent.children.append(self)

        self.ax = axis or self.parent.ax

        self.config = kwargs

        self.axis_manipulation()
        self.__post_init__()

    @property
    def properties(self) -> dict:
        return self.parent.properties

    @property
    def artists(self) -> dict:
        return self.parent.artists

    @property
    def params(self) -> dict:
        return self.parent.params

    def _set_background(self) -> None:
        raise NotImplementedError

    def _init_results(self) -> None:
        raise NotImplementedError

    def _reset_results(self) -> None:
        raise NotImplementedError

    def set_result(self, *args) -> None:
        raise NotImplementedError
