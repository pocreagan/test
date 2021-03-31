import functools
import time
from math import acos
from math import sqrt
from pickle import load as p_load
from typing import *

from matplotlib.collections import LineCollection
from matplotlib.patches import FancyBboxPatch
from matplotlib.transforms import Bbox
from PIL import Image

from framework.model import logger

__all__ = [
    'make_info_box',
    'make_bounds',
    'make_hatch',
    'duv',
    'cct',
    'img_from_pickle',
    'clear_garbage',
    'timer',
]

log = logger(__name__)

CORNER = .05
PAD_IN = .15


def make_info_box(corner: float = CORNER, pad_in: float = PAD_IN, **kwargs) -> FancyBboxPatch:
    box = Bbox([[corner, corner], [(1 - corner), (1 - corner)]])

    # SUPPRESS-LINTER <definitely correct>
    # noinspection PyTypeChecker
    return FancyBboxPatch(
        (box.xmin, box.ymin),
        abs(box.width),
        abs(box.height),
        boxstyle="round, pad=%f" % pad_in,
        **kwargs,
    )


def make_bounds(ax, colors, lines: list[list[tuple[float, ...]]]):
    return ax.add_collection(LineCollection(lines, color=colors, lw=1, zorder=-1,
                                            alpha=0.5, linestyle='dashed', dashes=(0, (5, 5))))


def make_hatch(ax, color: str, top_left, bottom_right) -> None:
    (top, left), (bottom, right) = top_left, bottom_right
    xs = left, right, right, left
    ys = bottom, bottom, top, top
    ax.fill(xs, ys, fill=False, hatch='xxx', color=color, linewidth=0, alpha=0.2)


def duv(x, y) -> float:
    u = (4 * x) / (-2 * x + 12 * y + 3)
    v = (6 * y) / (-2 * x + 12 * y + 3)
    k6 = -0.00616793
    k5 = 0.0893944
    k4 = -0.5179722
    k3 = 1.5317403
    k2 = -2.4243787
    k1 = 1.925865
    k0 = -0.471106
    lfp = sqrt(((u - 0.292) ** 2) + ((v - 0.24) ** 2))
    a = acos((u - 0.292) / lfp)
    lbb = k6 * (a ** 6) + k5 * (a ** 5) + k4 * (a ** 4) + k3 * (a ** 3) + k2 * (a ** 2) + k1 * a + k0
    return lfp - lbb


def cct(x, y) -> float:
    n = (x - 0.3320) / (0.1858 - y)
    return 437 * n ** 3 + 3601 * n ** 2 + 6861 * n + 5517


def img_from_pickle(fp: str) -> Image:
    with open(fp, 'rb') as pf:
        return Image.fromarray(p_load(pf))


def clear_garbage(ax):
    ax.set_ylim(0, 1.0)
    ax.set_xlim(0, 1.0)
    ax.axis('off')


def make_timer():
    _timer = time.perf_counter

    def timer_f(f: Callable):
        @functools.wraps(f)
        def inner(self, *args, **kwargs):
            ti = _timer()
            f(self, *args, **kwargs)
            tf = _timer()
            te = round((tf - ti) * 1000, 1)
            log.info(f'{self.name}.{f.__name__} took {te}ms to execute')

        return inner

    return timer_f


timer = make_timer()
