from typing import List

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from matplotlib.transforms import Bbox

from src.base.log import logger
from src.view.chart.base import Region

log = logger(__name__)

__all__ = [
    'RoundedTextOneLine',
    'RoundedTextMultiLine',
]


class RoundedText(Region):
    pad_in = 0.05
    corner = 0.15

    def axis_manipulation(self) -> None:
        pass

    def __post_init__(self) -> None:
        self.bbox = Bbox([[self.corner] * 2, [(1 - self.corner)] * 2])

    def make_box(self) -> FancyBboxPatch:
        raise NotImplementedError

    def make_label(self, *args) -> plt.Text:
        raise NotImplementedError

    def _set_background(self) -> None:
        raise NotImplementedError

    def _init_results(self) -> None:
        raise NotImplementedError

    def set_result(self, *args) -> None:
        raise NotImplementedError

    def _reset_results(self) -> None:
        raise NotImplementedError


class RoundedTextOneLine(RoundedText):
    _initial_text: str
    _initial_color: str

    def axis_manipulation(self) -> None:
        pass

    def _init_results(self) -> None:
        _name = self.__class__.__name__
        self.artists[_name] = {
            'box': self.var(self.ax.add_patch(self.make_box())),
            'text': self.var(self.make_label()),
        }

    def set_result(self, status: str = None, color: str = None) -> None:
        _name = self.__class__.__name__
        if status is not None:
            self.artists[_name]['text'].set_text(status)
        if color:
            self.artists[_name]['box'].set_facecolor(color)

    def _reset_results(self) -> None:
        _name = self.__class__.__name__
        self.artists[_name]['box'].set_facecolor(self._initial_color)
        self.artists[_name]['text'].set_text(self._initial_text)

    def _set_background(self) -> None:
        pass

    def make_box(self) -> FancyBboxPatch:
        raise NotImplementedError

    def make_label(self) -> plt.Text:
        raise NotImplementedError


class RoundedTextMultiLine(RoundedText):
    scaling_factor_y: float
    names: List[str]

    x_values: List[float]
    color_values: List[str]
    fonts: List
    alphas: List[float]
    horizontal_justifications: List[str]

    def axis_manipulation(self) -> None:
        pass

    @property
    def key(self) -> str:
        return self.config['channel_name']

    def make_y(self, i: int) -> float:
        raise NotImplementedError

    def make_box(self) -> FancyBboxPatch:
        raise NotImplementedError

    @property
    def spec(self) -> List[str]:
        raise NotImplementedError

    def __post_init__(self) -> None:
        RoundedText.__post_init__(self)
        self.artists['channels'][self.key] = {}

    def _set_background(self) -> None:
        self.ax.add_patch(self.make_box())
        self.make_label(self.key, False)

    def _init_results(self) -> None:
        self.make_label(self.key, True)

    def _reset_results(self) -> None:
        color = self.color_values[0]
        for label in self.artists['channels'][self.key].values():
            label.set_text('')
            label.set_color(color)

    def set_result(self, param: str, value, color: str = None) -> None:
        label = self.artists['channels'][self.key][param]
        label.set_text(str(value))
        if color:
            label.set_color(color)

    def make_label(self, ch: str, foreground: bool):
        j = int(not foreground)
        for i, (s, n) in enumerate(zip(self.spec, self.names)):
            label = self.ax.text(
                self.x_values[j],
                self.make_y(i),
                ['', s][j],
                ha=self.horizontal_justifications[j],
                va='center',
                color=self.color_values[j],
                fontproperties=self.fonts[j],
                transform=self.ax.transAxes,
                alpha=self.alphas[j],
            )
            if not j:
                self.artists['channels'][ch][n] = self.var(label)
