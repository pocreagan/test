from datetime import datetime
from typing import List

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from src.base.log import logger
from src.view.chart import font
from src.view.chart import helper
from src.view.chart.abstract_widgets import RoundedTextOneLine
from src.view.chart.base import *

log = logger(__name__)

UNIT_OFFSET = 0.15
unit_extent = [UNIT_OFFSET, 1 - UNIT_OFFSET, UNIT_OFFSET * 2, 1]

FILE_DATA_FONT = font.normal(12)
CHART_LABELS_FONT = font.normal(11)
UNIT_LABELS_FONT = font.bold(30)

unit_img_fp = r'C:\Projects\test_framework\src\framework\model\resources\img\10-00{mn}.p'


class UnitInfo(Region):
    def axis_manipulation(self) -> None:
        helper.clear_garbage(self.ax)
        self.ax.set(aspect="equal")

    def _set_background(self) -> None:
        self.ax.imshow(
            helper.img_from_pickle(unit_img_fp.format(mn=self.properties['mn'])),
            origin='upper', extent=unit_extent, alpha=0.5, zorder=-1
        )

    def _init_results(self) -> None:
        # TODO: add <option> display
        _kwargs = dict(ha='center', va='center', color='white')
        self.artists['unit_data'] = {
            'sn_mn': self.var(self.ax.text(
                0.5, 0.5 + UNIT_OFFSET - 0.03, '', **_kwargs, fontproperties=UNIT_LABELS_FONT
            )), 'timestamp': self.var(self.ax.text(
                0.5, 0 + 0.15, '', **_kwargs, fontproperties=CHART_LABELS_FONT
            ))
        }

    def set_result(self, timestamp: datetime = None, sn: int = None, mn: int = None) -> None:
        # TODO: CFG map 938 -> '10-00938'
        self.artists['unit_data']['sn_mn'].set_text(f'{mn}\n{sn}')
        self.artists['unit_data']['timestamp'].set_text(str(timestamp).split('.')[0])

    def _reset_results(self) -> None:
        self.artists['unit_data']['sn_mn'].set_text('')
        self.artists['unit_data']['timestamp'].set_text('')


class ConfigData(Region):
    def axis_manipulation(self) -> None:
        helper.clear_garbage(self.ax)

    def _set_background(self) -> None:
        pass

    def _init_results(self) -> None:
        self.artists['config_data'] = self.var(
            self.ax.text(
                .5, .5, '',
                ha='center', va='center', color='white',
                fontproperties=FILE_DATA_FONT, zorder=10
            )
        )

    def set_result(self, config_items: List[str]) -> None:
        _data = '\n'.join(config_items)
        self.artists['config_data'].set_text(_data)

    def _reset_results(self) -> None:
        self.artists['config_data'].set_text('')


class TestStatus(RoundedTextOneLine):
    _initial_text = 'TESTING'
    _initial_color = 'w'

    def axis_manipulation(self) -> None:
        helper.clear_garbage(self.ax)

    def make_box(self) -> FancyBboxPatch:
        # noinspection PyTypeChecker
        return FancyBboxPatch(
            (self.bbox.xmin, self.bbox.ymin),
            abs(self.bbox.width),
            abs(self.bbox.height),
            boxstyle="round, pad=%f" % self.pad_in,
            linewidth=1,
            facecolor=self._initial_color,
            alpha=0.3,
        )

    def make_label(self) -> plt.Text:
        return self.ax.text(
            0.5,
            0.5 - 0.03,
            self._initial_text,
            ha='center',
            va='center',
            color='white',
            fontproperties=UNIT_LABELS_FONT
        )
