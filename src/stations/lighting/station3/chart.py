import collections
from itertools import chain
from operator import attrgetter
from typing import *

import matplotlib
import matplotlib.axes
from matplotlib.collections import PatchCollection
from matplotlib.patches import Circle
from matplotlib.patches import FancyBboxPatch
from singledispatchmethod import singledispatchmethod

from src.model.db.schema import EEPROMConfigIteration
from src.model.db.schema import FirmwareIteration
from src.base.log import logger
from src.model.db import connect
from src.model.db.schema import LightingDUT
from src.model.db.schema import LightingStation3Iteration
from src.model.db.schema import LightingStation3LightMeasurement
from src.model.db.schema import LightingStation3Param
from src.model.db.schema import LightingStation3ParamRow
from src.model.db.schema import LightingStation3ResultRow
from src.model.resources import RESOURCE
from src.view.chart import colors
from src.view.chart import font
from src.view.chart import helper
from src.view.chart.abstract_widgets import RoundedTextMultiLine
from src.view.chart.base import *
from src.view.chart.concrete_widgets import ConfigData
from src.view.chart.concrete_widgets import TestStatus
from src.view.chart.concrete_widgets import UnitInfo
from src.view.chart.debug_window import ChartDebugWindow

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

_string_colors = {
    'Full On': colors.CH_COLORS['T100'],
    'Red': colors.CH_COLORS['R100'],
    'Green': colors.CH_COLORS['G100'],
    'Blue': colors.CH_COLORS['B100'],
    'Lime': colors.CH_COLORS['L100'],
    'White': colors.CH_COLORS['W100'],
}


def _make_string_color(param_row: LightingStation3ParamRow) -> str:
    return _string_colors[param_row.name]


class CIE(Region):
    params: List[LightingStation3ParamRow]
    current_param: LightingStation3ParamRow

    OFF_SCREEN = -1, -1

    def axis_manipulation(self) -> None:
        pass

    def __post_init__(self) -> None:
        [self.artists.__setitem__(
            param_row.id, dict()
        ) for param_row in self.params]

    def _set_background(self) -> None:
        self.ax.imshow(
            helper.img_from_pickle(RESOURCE.img('colorspace.p')),
            origin='upper', extent=cie_extent, alpha=1, zorder=10
        )
        patches = [
            Circle(
                (x + CIE_X_OFFSET, y + CIE_Y_OFFSET), r, linewidth=0.5
            ) for x, y, r in zip(*[[
                getattr(param_row, k) for param_row in self.params
            ] for k in ['x_nom', 'y_nom', 'color_dist_max']
            ])
        ]

        self.artists['params_collection'] = self.var(self.ax.add_collection(PatchCollection(
            patches, linewidths=0.5, facecolors=IP_FACE_COLOR, alpha=0.4, zorder=11
        )))

    def _init_results(self) -> None:
        self.artists['cie'] = {param_row.id: self.var(self.ax.add_patch(
            Circle(
                self.OFF_SCREEN,
                _make_string_color(param_row)[-1], alpha=0.7, edgecolor=IP_FACE_COLOR,
                facecolor=_make_string_color(param_row)[0],
                fill=True, linewidth=1, zorder=12,
            )
        )) for param_row in self.params}

    def start_string(self, param_row: LightingStation3ParamRow) -> None:
        self.current_param = param_row

    def set_result(self, meas: LightingStation3ResultRow) -> None:
        self.artists['cie'][self.current_param.id].center = (
            meas.x + CIE_X_OFFSET, meas.y + CIE_Y_OFFSET
        )

    def _reset_results(self) -> None:
        for circle in self.artists['cie'].values():
            circle.center = self.OFF_SCREEN


class Thermal(Region):
    params: List[LightingStation3ParamRow]
    current_param: LightingStation3ParamRow

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
        self.artists['therm'] = {param_row.id: self.var(self.ax.plot(
            self.artists['x_results_d'][param_row.id],
            self.artists['y_results_d'][param_row.id],
            marker='',
            color=_make_string_color(param_row)[0],
            linewidth=THERMAL_CHART_LINE_W_PX,
            alpha=THERMAL_CHART_LINE_ALPHA
        )[0]) for param_row in self.params}

    def start_string(self, param_row: LightingStation3ParamRow) -> None:
        self.current_param = param_row

    def set_result(self, meas: LightingStation3LightMeasurement) -> None:
        x = self.artists['x_results_d'][self.current_param.id]
        y = self.artists['y_results_d'][self.current_param.id]
        x.append(((meas.te / self.current_param.duration) * THERM_DX) + THERM_XI)
        y.append(((1 - ((meas.pct_drop * 100) / self.current_param.pct_drop_max)) * THERM_DY) + THERM_YI)
        self.artists['therm'][self.current_param.id].set_data(x, y)

    def _reset_results(self) -> None:
        [self.artists[k].clear() for k in ['x_results_d', 'y_results_d']]
        for ch, plot in self.artists['therm'].items():
            plot.set_data(self.artists['x_results_d'][ch],
                          self.artists['y_results_d'][ch])

    def populate_from_list(self, measurements: List[LightingStation3LightMeasurement]) -> None:
        x = self.artists['x_results_d'][self.current_param.id]
        y = self.artists['y_results_d'][self.current_param.id]
        x.clear()
        y.clear()
        duration = self.current_param.duration
        drop_max = self.current_param.pct_drop_max

        te_multiplier = THERM_DX / duration
        drop_multiplier = 100 / drop_max

        for meas in measurements:
            x.append((meas.te * te_multiplier) + THERM_XI)
            y.append(((1 - (meas.pct_drop * drop_multiplier)) * THERM_DY) + THERM_YI)

        self.artists['therm'][self.current_param.id].set_data(x, y)


class BarChart(Region):
    params: List[LightingStation3ParamRow]
    current_param: LightingStation3ParamRow

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
                    chain(*[
                        [_make_string_color(param_row)[0]] * 2 for param_row in self.params
                    ])
                ),
                alpha=THERMAL_CHART_LINE_ALPHA,
            )), 'indices': {param_row.id: {
                'fcd': (2 * (i + 1)),
                'p': (2 * (i + 1)) + 1
            } for i, param_row in enumerate(self.params)}
        }

    def start_string(self, param_row: LightingStation3ParamRow) -> None:
        self.current_param = param_row

    def set_result(self, meas: LightingStation3ResultRow):
        for k, index in self.artists['bar']['indices'][self.current_param.id].items():
            nom = getattr(self.current_param, f'{k}_nom')
            tol = getattr(self.current_param, f'{k}_tol')
            self.artists['bar']['collection'][index].set_width((getattr(meas, k) - nom) / tol)

    def _reset_results(self):
        for d in self.artists['bar']['indices'].values():
            [self.artists['bar']['collection'][i].set_width(0.) for i in d.values()]


class WhiteCalculations(RoundedTextMultiLine):
    params: List[LightingStation3ParamRow]
    current_param: LightingStation3ParamRow

    scaling_factor_y = 0.3
    names = ['cct', 'duv']
    x_values = [0.4, 0.60]
    alphas = [1., 1.]
    fonts = [FILE_DATA_FONT] * 2
    color_values = [IP_FACE_COLOR] * 2
    horizontal_justifications = ['center'] * 2

    @property
    def key(self) -> str:
        return self.config['current_param'].id

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

    def set_from_color_point(self, meas: LightingStation3ResultRow) -> None:
        self.set_result('cct', r'$ %0d $' % meas.CCT)
        self.set_result('duv', r'$ %0.3f $' % meas.duv)


class ChannelInfo(RoundedTextMultiLine):
    params: List[LightingStation3ParamRow]
    current_param: LightingStation3ParamRow
    scaling_factor_y = 0.55
    names = ['dist', 'fcd', 'P', 'drop']

    x_values = [0.22, 0.60]
    alphas = [0.7, 1.]

    color_values = ['#00ff00', 'w']
    fonts = [CH_INFO_FONT_VALUE] * 2
    horizontal_justifications = ['center'] * 2

    def __post_init__(self) -> None:
        RoundedTextMultiLine.__post_init__(self)
        self.current_param = self.config['current_param']

    @property
    def key(self) -> str:
        return self.config['current_param'].id

    def axis_manipulation(self) -> None:
        helper.clear_garbage(self.ax)

    def make_y(self, i: int) -> float:
        return (0.5 + (self.scaling_factor_y / 2)) - ((self.scaling_factor_y / 3) * i)

    @property
    def spec(self) -> List[str]:
        spec = [
            r'$ dist < %.3f $' % self.current_param.color_dist_max,
            r'$ %.1f < E_v < %.1f fcd $' % (
                self.current_param.fcd_nom - self.current_param.fcd_tol,
                self.current_param.fcd_nom + self.current_param.fcd_tol
            ),
            r'$ %.1f < P < %.1f W $' % (
                self.current_param.p_nom - self.current_param.p_tol,
                self.current_param.p_nom + self.current_param.p_tol
            ),
            r'$ drop < %.2f / %.1f s $' % (
                self.current_param.pct_drop_max, self.current_param.duration
            ),
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
            edgecolor=_make_string_color(self.current_param)[0],
            linewidth=1,
            facecolor=None,
            alpha=THERMAL_CHART_LINE_ALPHA,
        )

    def set_value(self, meas: LightingStation3ResultRow) -> None:
        self.set_result('dist', f'$ {meas.cie_dist:.3f} $',
                        color='#00ff00' if meas.cie_pf else '#ff0000')
        self.set_result('fcd', f'$ {meas.fcd:.1f} $',
                        color='#00ff00' if meas.fcd_pf else '#ff0000')
        self.set_result('P', f'$ {meas.p:.1f} $',
                        color='#00ff00' if meas.p_pf else '#ff0000')
        self.set_result('drop', f'$ {meas.pct_drop:.2f} $',
                        color='#00ff00' if meas.pct_drop_pf else '#ff0000')


class BigChart(Region):
    params: List[LightingStation3ParamRow]

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
    params: List[LightingStation3ParamRow]
    current_param: LightingStation3ParamRow
    white_quality: WhiteCalculations = None
    param_row_index: int = 0

    def _add_info_box(self, top: int, cla: INFO_BOX_T,
                      param: LightingStation3ParamRow) -> Tuple[int, INFO_BOX]:
        bottom = top + 16
        return bottom, cla(self, self.fig.add_subplot(self.gs[top:bottom, 90:125]), current_param=param)

    def increment_param_row(self) -> None:
        self.param_row_index += 1
        try:
            self.set_attr_propagate(
                'current_param', self.params[self.param_row_index]
            )
        except IndexError:
            pass

    def init_results(self) -> None:
        self.param_row_index: int = -1
        self.increment_param_row()
        super().init_results()

    def __post_init__(self) -> None:
        self.big_chart = BigChart(self, self.fig.add_subplot(self.gs[:, :90]))
        self.bar_chart = BarChart(self, self.fig.add_subplot(self.gs[40:90, 60:90]))
        self.unit_info = UnitInfo(self, self.fig.add_subplot(self.gs[2:37, 125:]))
        self.config_data = ConfigData(self, self.fig.add_subplot(self.gs[60:74, 125:]))
        self.test_status = TestStatus(self, self.fig.add_subplot(self.gs[74:88, 125:]))

        self.artists['channels'] = {}
        top_offset, _bottom, self.channel_info = 5, None, dict()

        for i, param in enumerate(self.params):
            _top = top_offset + (i * 16)
            _bottom, widget = self._add_info_box(_top, ChannelInfo, param)
            self.channel_info[param.id]: ChannelInfo = widget

        # self.white_quality: WhiteCalculations = self._add_info_box(
        #     69, WhiteCalculations, first
        # )[-1]

    @singledispatchmethod
    def update(self, msg):
        raise ValueError(f'type {type(msg)} {msg} not recognized')

    @update.register
    def _(self, msg: LightingStation3Iteration) -> None:
        self.test_status.set_result_from_iteration(msg)
        fw_iterations: List[FirmwareIteration] = msg.firmware_iterations
        cfg_iterations: List[EEPROMConfigIteration] = msg.config_iterations
        config_info = [f'v{fw.firmware.version}' for fw in fw_iterations]
        config_info.extend(cfg.config.name for cfg in cfg_iterations)
        self.config_data.set_result(config_info)

    @update.register
    def _(self, msg: LightingDUT) -> None:
        self.unit_info.set_result(f'option: {msg.option}', msg.sn, msg.mn)

    @update.register
    def _(self, msg: LightingStation3LightMeasurement) -> None:
        self.big_chart.thermal.set_result(msg)

    @update.register
    def _(self, msg: LightingStation3ResultRow) -> None:
        self.big_chart.cie.set_result(msg)
        self.channel_info[self.current_param.id].set_value(msg)
        self.bar_chart.set_result(msg)
        self.increment_param_row()

        # TODO: white quality might need implemented
        # if 'W' in k:
        #     self.white_quality.set_from_color_point(x, y)

    def populate_from_iteration(self, record: LightingStation3Iteration) -> None:
        self.update(record.dut[0])
        for meas in iteration.result_rows:  # type: LightingStation3ResultRow
            thermal: List[LightingStation3LightMeasurement] = measurement.light_measurements
            self.big_chart.thermal.populate_from_list(thermal)
            self.update(meas)
        self.update(iteration)
        self.draw_artists()


if __name__ == '__main__':
    with logger:
        with connect(echo_sql=False)(expire=False) as session:
            params = LightingStation3Param.get(session, '918 brighter')
            rows = list(sorted(params.rows, key=attrgetter('row_num')))
            iteration: LightingStation3Iteration = session.query(LightingStation3Iteration).first()
            dut = LightingDUT(sn=9000000, mn=918, option='bright')
            messages = [dut]
            for measurement in iteration.result_rows:  # type: LightingStation3ResultRow
                messages.extend([*measurement.light_measurements, measurement])
            messages.append(iteration)
            window = ChartDebugWindow(Plot(rows, mn=dut.mn), messages).mainloop()
