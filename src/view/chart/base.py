import tkinter as tk
from itertools import chain
from pathlib import Path
from typing import *

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import cbook
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.image import FigureImage

from src.base.log import logger
from src.view.chart.helper import timer
from src.view.chart.helper import matplotlib_config

log = logger(__name__)

__all__ = [
    'Root',
    'Region',
]

ANIMATED_ARTISTS = List[plt.Artist]
VARIABLE_OBJ = Union[plt.Artist, Iterable[plt.Artist]]
ITERATION_DATA = Any
PATH_LIKE = Union[str, Path]

_T = TypeVar('_T', bound=VARIABLE_OBJ)


class Widget:
    def __post_init__(self) -> None:
        pass

    def __init__(self) -> None:
        self.name = self.__class__.__name__
        self.children = list()
        self._variables = list()
        self.__animated = list()

    def var(self, obj: _T) -> _T:
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

    def _propagate(self, f: str, *args, **kwargs) -> None:
        """
        perform method on self, then on children
        then if <method>_after is defined, performs it
        """
        getattr(self, f'_{f}')(*args, **kwargs)
        [getattr(child, f)(*args, **kwargs) for child in self.children]
        method = getattr(self, f'_{f}_after', None)
        if callable(method):
            method(*args, **kwargs)

    def set_attr_propagate(self, k: str, v: _T) -> _T:
        setattr(self, k, v)
        [child.set_attr_propagate(k, v) for child in self.children]
        return v

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


class Root(Widget, Generic[_T]):
    tk_widget: Optional[tk.Frame]
    canvas: Optional[FigureCanvasTkAgg]
    background_img: Optional[FigureImage]

    def __init__(self, params: _T, w: int = 1429, h: int = 799,
                 dpi: int = 141, color: str = '#000000', **kwargs) -> None:
        Widget.__init__(self)

        self.params = params
        self.w = w
        self.h = h
        self.dpi = dpi
        self.face_color = color

        matplotlib_config()

        self.fig: plt.Figure = plt.figure(
            figsize=(self.w / self.dpi, self.h / self.dpi),
            dpi=self.dpi, facecolor=self.face_color,
        )

        self.gs = self.fig.add_gridspec(
            nrows=90, ncols=160, left=0, right=1, top=1, bottom=0, hspace=0, wspace=0
        )

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
        self.draw_artists()

    def draw_artists(self) -> None:
        self.canvas.restore_region(self._bg)
        list(map(self.canvas.figure.draw_artist, self.animated))
        self.canvas.blit(self.canvas.figure.bbox)

    def __call__(self, iteration_data: List[ITERATION_DATA]):
        if hasattr(iteration_data, '__iter__'):
            list(map(self.update, iteration_data))
        else:
            self.update(iteration_data)
        self.draw_artists()

    def _set_background(self) -> None:
        pass

    def populate_from_iteration(self, iteration) -> None:
        raise NotImplementedError

    def _init_results(self) -> None:
        pass

    def set_result(self, *args) -> None:
        pass

    def _reset_results(self) -> None:
        pass


class Region(Widget, Generic[_T]):
    def axis_manipulation(self) -> None:
        raise NotImplementedError

    def __init__(self, parent: Union['Region[_T]', Root[_T]], axis: plt.Axes = None, **kwargs) -> None:
        Widget.__init__(self)

        self.parent = parent
        self.parent.children.append(self)

        self.ax: plt.Axes = axis or self.parent.ax

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
    def params(self) -> _T:
        return self.parent.params

    def _set_background(self) -> None:
        raise NotImplementedError

    def _init_results(self) -> None:
        raise NotImplementedError

    def _reset_results(self) -> None:
        raise NotImplementedError

    def set_result(self, *args) -> None:
        raise NotImplementedError
