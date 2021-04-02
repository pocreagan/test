import collections
import functools
from itertools import chain
from math import sqrt
from typing import *

import matplotlib
from matplotlib.collections import PatchCollection
from matplotlib.patches import Circle
from matplotlib.patches import FancyBboxPatch

from model.db.schema import LightingStation3LightMeasurement
from model.db.schema import LightingStation3ParamRow
from src.model.resources import RESOURCE
from src.base.log import logger
from src.view.chart import colors
from src.view.chart import font
from src.view.chart import helper
from src.view.chart.abstract_widgets import RoundedTextMultiLine
from src.view.chart.base import *
from src.view.chart.concrete_widgets import ConfigData
from src.view.chart.concrete_widgets import TestStatus
from src.view.chart.concrete_widgets import UnitInfo
from src.model.db import schema
from stations.lighting.station3.model import Station3TestModel

log = logger(__name__)

matplotlib.use("TkAgg")
matplotlib.rcParams['toolbar'] = 'None'
matplotlib.rcParams['font.family'] = 'Linotype Univers 430 Regular'

STEP_RIGHT_EDGE = .25
THERM_XI = .05
THERM_XF = 1.15
THERM_YI = 0.75
THERM_YF = 1.15
THERM_DX = THERM_XF - THERM_XI
THERM_DY = THERM_YF - THERM_YI

THERMAL_CHART_LINE_W_PX = 1
THERMAL_CHART_LINE_ALPHA = 0.8

CIE_X_OFFSET = THERM_XI
CIE_Y_OFFSET = .05
cie_extent = [0.00, 0.74, 0.00, 0.835]
cie_extent = [x + [CIE_X_OFFSET, CIE_Y_OFFSET][i // 2]
              for i, x in enumerate(cie_extent)]

UNIT_OFFSET = 0.15
unit_extent = [UNIT_OFFSET, 1 - UNIT_OFFSET, UNIT_OFFSET * 2, 1]

THERMAL_UNITS_LABEL = r'$max -\Delta E_v / \Delta t$'

POWER_ILLUMINANCE_UNITS_LABELS = [r'$E_v$', r'$P$']
POWER_ILLUMINANCE_BAR_LABELS = [r'$+ tol$', r'$- tol$']

COMPLETE_FACE_COLOR = (0.05, 0.05, 0.05)
IP_FACE_COLOR = (0.1, 0.1, 0.1)
TESTING_COLOR = (0, 0, 1, 1)

BAR_LABELS_FONT = font.normal(8)
FILE_DATA_FONT = font.normal(12)
CHART_LABELS_FONT = font.normal(11)
CH_INFO_FONT_VALUE = font.bold(8)
CH_INFO_FONT_SPEC = font.normal(8)

__all__ = [
    'Plot',
]


class CIE(Region):
    params: Station3TestModel
    OFF_SCREEN = -1, -1

    def axis_manipulation(self) -> None:
        pass

    def __post_init__(self) -> None:
        [self.artists.__setitem__(k, dict()) for k in self.params.keys()]

    def _set_background(self) -> None:
        self.ax.imshow(
            helper.img_from_pickle(RESOURCE.img('colorspace.p')),
            origin='upper', extent=cie_extent, alpha=1, zorder=10
        )
        patches = [
            Circle(
                (x + CIE_X_OFFSET, y + CIE_Y_OFFSET), r, linewidth=0.5
            ) for x, y, r in zip(*[[
                    d['color_point'][k] for d in self.params.values()
                ] for k in ['x_nom', 'y_nom', 'dist']
            ])
        ]

        self.artists['params_collection'] = self.var(self.ax.add_collection(PatchCollection(
            patches, linewidths=0.5, facecolors=IP_FACE_COLOR, alpha=0.4, zorder=11
        )))

    def _init_results(self) -> None:
        self.artists['cie'] = {k: self.var(self.ax.add_patch(
            Circle(
                self.OFF_SCREEN,
                colors.CH_COLORS[k][-1], alpha=0.7, edgecolor=IP_FACE_COLOR,
                facecolor=colors.CH_COLORS[k][0],
                fill=True, linewidth=1, zorder=12,
            )
        )) for k in self.params.keys()}

    def set_result(self, ch: str, x: float, y: float) -> None:
        self.artists['cie'][ch].center = x + CIE_X_OFFSET, y + CIE_Y_OFFSET

    def _reset_results(self) -> None:
        for circle in self.artists['cie'].values():
            circle.center = self.OFF_SCREEN


class Thermal(Region):
    params: Station3TestModel
    l1 = [(THERM_XI, THERM_YF), (THERM_XF, THERM_YF)]
    l2 = [(THERM_XI, THERM_YI), (THERM_XF, THERM_YI)]

    def axis_manipulation(self) -> None:
        pass

    def __post_init__(self) -> None:
        [self.artists.__setitem__(k, collections.defaultdict(list)) for k in ['x_results_d', 'y_results_d']]

    def _set_background(self) -> None:
        helper.make_hatch(self.ax, 'r', (THERM_YI, .1), (THERM_YI - .05, THERM_XF))
        helper.make_bounds(self.ax, ['w', 'r'], [self.l1, self.l2])
        self.ax.text(
            ((THERM_XF - THERM_XI) / 2) + THERM_XI, THERM_YI - .01, THERMAL_UNITS_LABEL,
            ha='center', va='top', color='white',
            fontproperties=CHART_LABELS_FONT
        )

    def _init_results(self) -> None:
        self.artists['initial_fcd_d'] = dict()
        self.artists['therm'] = {param_row.id: self.var(self.ax.plot(
            self.artists['x_results_d'][param_row.id],
            self.artists['y_results_d'][param_row.id],
            marker='',
            color=colors.CH_COLORS[param_row.id][0],
            linewidth=THERMAL_CHART_LINE_W_PX,
            alpha=THERMAL_CHART_LINE_ALPHA
        )[0]) for param_row in self.params.string_params_rows}

    def set_result(self, param_row: LightingStation3ParamRow,
                    meas: LightingStation3LightMeasurement) -> Optional[bool]:
        initial_fcd = self.artists['initial_fcd_d'].setdefault(param_row.id, meas.fcd)

        dt = (self.params[param_row.id]['thermal']['dt'] * 10)
        max_drop = self.params[param_row.id]['thermal']['max_pct'] / 100

        y = self.artists['y_results_d'][param_row.id]
        x = self.artists['x_results_d'][param_row.id]

        drop = ((initial_fcd - meas.fcd) / initial_fcd)

        y.append(((len(y) / (dt - 1)) * THERM_DX) + THERM_XI)
        x.append((THERM_DY * (1 - (drop / max_drop))) + THERM_YI)
        self.artists['therm'][param_row.id].set_data(y, x)

        if len(y) == dt:
            return drop

    def _reset_results(self) -> None:
        self.artists['initial_fcd_d'].clear()
        [self.artists[k].clear() for k in ['x_results_d', 'y_results_d']]
        for ch, plot in self.artists['therm'].items():
            plot.set_data(self.artists['x_results_d'][ch],
                          self.artists['y_results_d'][ch])


class BarChart(Region):
    params: Station3TestModel
    RIGHT_TOP = (1, 0)
    LEFT_TOP = (-1, 0)

    def axis_manipulation(self) -> None:
        helper.clear_garbage(self.ax)
        self.ax.set_xlim(-1.5, 1.5)

    def _scale(self, num_channels: int) -> Tuple[int, float]:
        y_max = 3 * num_channels
        pad_out = (THERM_XI / 1.2) * y_max * 2
        self.ax.set_ylim(-pad_out, y_max + pad_out)
        self.ax.invert_yaxis()
        return y_max, pad_out

    def _set_background(self) -> None:
        y_max, _ = self._scale(5)

        for txt, (x, y) in zip(POWER_ILLUMINANCE_BAR_LABELS, [self.RIGHT_TOP, self.LEFT_TOP]):
            self.ax.text(
                x * 1.125, y_max / 2, txt,
                ha='center', va='center', color='white',
                fontproperties=BAR_LABELS_FONT, rotation=90,
            )
            helper.make_hatch(self.ax, 'r', (0, x), (y_max, x * 1.25))

        l1 = [self.RIGHT_TOP, (1, y_max)]
        l2 = [self.LEFT_TOP, (-1, y_max)]
        helper.make_bounds(self.ax, ['r', 'r'], [l1, l2])

    def _init_results(self) -> None:
        num_channels = len(self.params) + 1
        y_max, pad_out = self._scale(num_channels)

        self.artists['bar'] = {
            'labels': {txt: self.var(self.ax.text(
                0, y, txt,
                ha='center', va='center', color='white',
                fontproperties=CHART_LABELS_FONT
            )) for txt, y in zip(POWER_ILLUMINANCE_UNITS_LABELS, [1, 2])
            }, 'collection': self.var(self.ax.barh(
                list(chain(*[(i, i + 1) for i in range(1, y_max, 3)])),
                [0] * (num_channels * 2),
                align='center',
                color=['b', 'b'] + list(
                    chain(*[[colors.CH_COLORS[k][0]] * 2 for k in self.params.keys()])),
                alpha=THERMAL_CHART_LINE_ALPHA,
            )), 'indices': {k: {
                'fcd': (2 * (i + 1)),
                'P': (2 * (i + 1)) + 1
            } for i, k in enumerate(self.params.keys())}
        }

    def set_result(self, ch: str, param: str, value: float):
        x = (value - self.params[ch][param]['nom']) / self.params[ch][param]['tol']
        self.artists['bar']['collection'][self.artists['bar']['indices'][ch][param]].set_width(x)

    def _reset_results(self):
        for d in self.artists['bar']['indices'].values():
            [self.artists['bar']['collection'][i].set_width(0.) for i in d.values()]


class WhiteCalculations(RoundedTextMultiLine):
    params: Station3TestModel
    scaling_factor_y = 0.3
    names = ['cct', 'duv']

    x_values = [0.4, 0.60]
    alphas = [1., 1.]

    fonts = [FILE_DATA_FONT] * 2
    color_values = [IP_FACE_COLOR] * 2
    horizontal_justifications = ['center'] * 2

    def axis_manipulation(self) -> None:
        helper.clear_garbage(self.ax)

    @property
    def spec(self) -> List[str]:
        return [
            r'$ CCT $',
            r'$ Duv $',
        ]

    def make_y(self, i: int) -> float:
        _factor = self.scaling_factor_y
        return (0.5 + (_factor / 2)) - (_factor * i)

    def make_box(self) -> FancyBboxPatch:
        # noinspection PyTypeChecker
        return FancyBboxPatch(
            (self.bbox.xmin, self.bbox.ymin),
            abs(self.bbox.width),
            abs(self.bbox.height),
            boxstyle="round, pad=%f" % self.pad_in,
            linewidth=THERMAL_CHART_LINE_W_PX,
            facecolor='w',
            alpha=1.0,
        )

    def set_from_color_point(self, x: float, y: float) -> None:
        self.set_result('cct', r'$ %0d $' % helper.cct(x, y))
        self.set_result('duv', r'$ %0.3f $' % helper.duv(x, y))


class ChannelInfo(RoundedTextMultiLine):
    params: Station3TestModel
    scaling_factor_y = 0.55
    names = ['dist', 'fcd', 'P', 'drop']

    x_values = [0.22, 0.60]
    alphas = [0.7, 1.]

    color_values = ['#00ff00', 'w']
    fonts = [CH_INFO_FONT_VALUE] * 2
    horizontal_justifications = ['center'] * 2

    def axis_manipulation(self) -> None:
        helper.clear_garbage(self.ax)

    def make_y(self, i: int) -> float:
        return (0.5 + (self.scaling_factor_y / 2)) - ((self.scaling_factor_y / 3) * i)

    @property
    def spec(self) -> List[str]:
        params = self.params[self.config['channel_name']]
        spec = [
            r'$ dist < %.3f $' % (params['color_point']['dist']),
            r'$ %.1f < E_v < %.1f fcd $' % (
                params['fcd']['nom'] - params['fcd']['tol'], params['fcd']['nom'] + params['fcd']['tol']),
            r'$ %.1f < P < %.1f W $' % (
                params['P']['nom'] - params['P']['tol'], params['P']['nom'] + params['P']['tol']),
            r'$ drop < %.2f / %.1f s $' % (params['thermal']
                                           ['max_pct'], params['thermal']['dt']),
        ]
        return spec

    def make_box(self) -> FancyBboxPatch:
        # noinspection PyTypeChecker
        return FancyBboxPatch(
            (self.bbox.xmin, self.bbox.ymin),
            abs(self.bbox.width),
            abs(self.bbox.height),
            boxstyle="round, pad=%f" % self.pad_in,
            fill=False,
            edgecolor=colors.CH_COLORS[self.config['channel_name']][0],
            linewidth=1,
            facecolor=None,
            alpha=THERMAL_CHART_LINE_ALPHA,
        )

    def set_value(self, param: str, value: float, is_pass: bool) -> None:
        self.set_result(param, r'$ ' + str(value) + r' $',
                        color='#00ff00' if is_pass else '#ff0000')


class BigChart(Region):
    params: Station3TestModel
    def _set_background(self) -> None:
        pass

    def _init_results(self) -> None:
        pass

    def set_result(self, *args) -> None:
        pass

    def _reset_results(self) -> None:
        pass

    def axis_manipulation(self) -> None:
        helper.clear_garbage(self.ax)
        self.ax.set_xlim(0, 1.2)
        self.ax.set_ylim(0, 1.2)
        self.ax.set(aspect="equal")

    def __post_init__(self):
        self.cie = CIE(self)
        self.thermal = Thermal(self)


INFO_BOX = Union[ChannelInfo, WhiteCalculations]
INFO_BOX_T = Type[INFO_BOX]
CALC_RESULT = Tuple[float, bool]


class Plot(Root):
    params: Station3TestModel

    def _add_info_box(self, top: int, cla: INFO_BOX_T, name: str) -> Tuple[int, INFO_BOX]:
        bottom = top + 16
        return bottom, cla(self, self.fig.add_subplot(self.gs[top:bottom, 90:125]), channel_name=name)

    def __post_init__(self) -> None:
        self.big_chart = BigChart(self, self.fig.add_subplot(self.gs[:, :90]))
        self.bar_chart = BarChart(self, self.fig.add_subplot(self.gs[40:90, 60:90]))
        self.unit_info = UnitInfo(self, self.fig.add_subplot(self.gs[2:37, 125:]))
        self.config_data = ConfigData(self, self.fig.add_subplot(self.gs[60:74, 125:]))
        self.test_status = TestStatus(self, self.fig.add_subplot(self.gs[74:88, 125:]))

        first, *rest = keys = self.params.string_params_rows
        self.artists['channels'] = {}
        top_offset, _bottom, self.channel_info = 5, None, dict()

        for i, k in enumerate(keys):
            _top = top_offset + (i * 16)
            _bottom, widget = self._add_info_box(_top, ChannelInfo, k.name)
            self.channel_info[k.name]: ChannelInfo = widget

        if not rest:
            self.white_quality: WhiteCalculations = self._add_info_box(69, WhiteCalculations, first)[-1]

    def _calc_nom_tol(self, ch: str, param: str, value) -> CALC_RESULT:
        param = self.params[ch][param]
        is_pass = ((param['nom'] - param['tol']) <
                   value < (param['nom'] + param['tol']))
        return round(value, 1), is_pass

    def _calc_dist(self, ch: str, param: str, value) -> CALC_RESULT:
        _ = param
        param = self.params[ch]['color_point']
        value = sqrt(((value[0] - param['x_nom']) ** 2) +
                     ((value[1] - param['y_nom']) ** 2))
        return round(value, 3), value < param['dist']

    def _calc_thermal(self, ch: str, param: str, value) -> CALC_RESULT:
        _ = param
        return round(value, 2), value < self.params[ch]['thermal']['max_pct']

    calculations = {
        'fcd': _calc_nom_tol,
        'P': _calc_nom_tol,
        'dist': _calc_dist,
        'drop': _calc_thermal,
    }

    def _add_result(self, ch, name, value):
        # SUPPRESS-LINTER <definitely good>
        # noinspection PyArgumentList
        self.channel_info[ch].set_value(name, *self.calculations[name](self, ch, name, value))

    @functools.singledispatchmethod
    def update(self, msg):
        raise ValueError(f'type {type(msg)} {msg} not recognized')

    @update.register
    def _(self, msg: schema.LightingStation3Iteration) -> None:
        self.test_status.set_result(msg.status, colors.STEP_PROGRESS_COLORS[msg.status])

    @update.register
    def _(self, msg: schema.LightingDUT) -> None:
        self.unit_info.set_result(msg.timestamp, msg.sn, msg.mn)
        self.config_data.set_result(msg.config)

    @update.register
    def _(self, msg: schema.LightingStation3LightMeasurement) -> None:
        drop = self.big_chart.thermal.set_result(msg.string_dmx, msg.fcd)
        if drop:
            self._add_result(msg.string_dmx, 'drop', drop * 100)

    @update.register
    def _(self, msg: schema.LightingStation3ResultRow) -> None:
        k, x, y = msg.string_dmx, msg.x, msg.y

        self._add_result(k, 'dist', [x, y])

        if 'W' in k:
            self.white_quality.set_from_color_point(x, y)

        self.big_chart.cie.set_result(k, x, y)

        for value, param in zip([msg.fcd, msg.W], ['fcd', 'P']):
            self._add_result(k, param, value)
            self.bar_chart.set_result(k, param, value)
