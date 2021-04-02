import itertools
import time
from datetime import datetime

import matplotlib.pyplot as plt
from PIL import Image

from framework.model.resources.temp.fake_data.LL2 import data

__all__ = [
    'main',
]

FONT_NAME = r'LinotypeUnivers-430Regular.tff'
LARGE_FONT = (FONT_NAME, 3, 'bold')
STATUS_FONT = (FONT_NAME, 2)
INTERVAL = 1
LABEL_X_OFFSET = 0.02
PSI_OFFSET = 0.13

COMPLETE_FACE_COLOR = (0.05, 0.05, 0.05)
IP_FACE_COLOR = (0.1, 0.1, 0.1)
TESTING_COLOR = (0, 0, 1)
RED = (1, 0, 0)
GRN = (0, 1, 0)

TIMER_OFFSET = 0.11

META_LABELS = [
    'MN: ',
    'SN: ',
    'UID: ',
    'Test:',
    'Date: ',
    'Time: ',
]


def get_x_min(duration):
    return -1 * (duration - 0.1)


def clear_axis(ax):
    from matplotlib.pyplot import NullLocator

    ax.set_ylabel('')
    ax.set_xlabel('')
    ax.grid(False)
    ax.xaxis.set_major_locator(NullLocator())
    ax.yaxis.set_major_locator(NullLocator())
    ax.xaxis.set_minor_locator(NullLocator())
    ax.yaxis.set_minor_locator(NullLocator())


def setup_chart(figure, lt, metadata):
    ti = time.perf_counter()

    logo = Image.open(r'C:\Projects\test_framework\src\framework\model\resources\img\wet_logo.png')
    metadata = metadata + (f'"{lt.test_prog}" ({lt.test_program})',)

    start_y_min = lt.test_pressure - lt.pressure_min
    start_y_max = lt.test_pressure + lt.pressure_min
    total_fill_time = lt.fast_fill_timer + lt.fill_timer
    total_time = sum([
        total_fill_time,
        lt.settle_timer,
        lt.test_timer,
        lt.vent_timer,
    ])

    stages = {
        'FILL': {
            'x_min': get_x_min(total_fill_time),
            'y_min': start_y_min,
            'y_max': start_y_max,
        },
        'SETTLE': {
            'x_min': get_x_min(lt.settle_timer),
            'y_min': start_y_min,
            'y_max': start_y_max,
        },
        'TEST': {
            'x_min': get_x_min(lt.test_timer),
            'y_min': 0.0,
            'y_max': 1.0,
        },
        'VENT': {
            'x_min': get_x_min(lt.vent_timer),
            'y_min': 0.0,
            'y_max': 1.0,
        },
    }

    axes, artists, points = {}, {}, {}

    gs = figure.add_gridspec(nrows=20, ncols=int(total_time * 10), left=0,
                             right=1, top=1, bottom=0, hspace=0, wspace=0)

    col = 0
    old_col = 0
    x_max = 0
    for stage, d in stages.items():
        x_max = int((-d['x_min']) + 0.1)
        top = 0
        if stage == 'VENT':
            top = 2
        _col = int(col * 10)
        ax: plt.Axes = figure.add_subplot(gs[top:, _col:_col + x_max * 10])
        ax.set_facecolor(COMPLETE_FACE_COLOR)
        ax.set_ylim(d['y_min'], d['y_max'])
        ax.set_xlim(d['x_min'], 0.0)
        clear_axis(ax)
        label: plt.Text = ax.text(
            LABEL_X_OFFSET,
            LABEL_X_OFFSET,
            stage,
            ha='left',
            va='bottom',
            color='white',
            weight='bold',
            size='12',
            fontname=FONT_NAME,
            transform=ax.transAxes,
        )
        plot = ax.plot(
            [],
            [],
            marker='',
            color=TESTING_COLOR,
            linewidth=1,
            alpha=1
        )

        if stage == 'VENT':
            artists[stage + '_TITLE'] = label
            d_date, d_time = str(datetime.now()).split('.')[0].split(' ')
            d_date, d_time = d_date.replace("-", ""), d_time.replace(":", "")
            labels = '\n'.join(META_LABELS)
            values = '\n'.join(metadata + (d_date, d_time))
            for j, txt in enumerate([labels, values]):
                label = ax.text(
                    [LABEL_X_OFFSET, 1 - LABEL_X_OFFSET][j],
                    1 - LABEL_X_OFFSET,
                    txt,
                    ha=['left', 'right'][j],
                    va='top',
                    color='white',
                    size='6',
                    fontname=FONT_NAME,
                    transform=ax.transAxes,
                )
                artists[txt + '_STATIC'] = label
        else:
            label: plt.Text = ax.text(
                1 - LABEL_X_OFFSET,
                1 - LABEL_X_OFFSET,
                '',
                ha='right',
                va='top',
                color='white',
                size='9',
                fontname=FONT_NAME,
                transform=ax.transAxes,
            )
            artists[stage + '_TEXT'] = label
        label = ax.text(
            LABEL_X_OFFSET,
            TIMER_OFFSET,
            '',
            ha='left',
            va='bottom',
            color='white',
            size='9',
            fontname=FONT_NAME,
            transform=ax.transAxes,
        )
        artists[stage + '_TIMER'] = label
        artists[stage] = plot
        axes[stage] = ax
        points[stage] = {'x': [], 'y': []}
        old_col = col
        col += x_max
    _col = int(old_col * 10)
    ax = figure.add_subplot(gs[0:2, _col:_col + x_max * 100])
    ax.set_facecolor(COMPLETE_FACE_COLOR)
    clear_axis(ax)
    ax.imshow(logo)

    tf = time.perf_counter()
    print(tf - ti)

    return figure, Animation(axes, artists, points, stages)


class Animation:
    def init_one_axis(self, stage: str) -> None:
        [self.points[stage][k].clear() for k in ['x', 'y']]
        self.artists[stage][0].set_data(self.points[stage]['x'], self.points[stage]['y'])

    def init(self):
        [self.init_one_axis(stage) for stage in self.stages]

    def __init__(self, axes, artists, points, stages):
        self.axes = axes
        self.artists = artists
        self.points = points
        self.stages = stages
        self.last_pressure = 0
        self.last_stage = 'VENT'
        self.last_text = ''
        self.last_timer = ''

    @staticmethod
    def sim_data():
        iterator = iter(data.fake_data)
        for _ in itertools.count():

            try:
                stage, x, y = next(iterator)

            except StopIteration:
                break

            else:
                yield [(str(stage), float(x), float(y))]

    def __call__(self, iteration_data):
        [self.update(i) for i in iteration_data]

    def complete_stage(self) -> None:
        self.artists[self.last_stage + '_TIMER'].set_text('')
        self.axes[self.last_stage].set_facecolor(COMPLETE_FACE_COLOR)

    def test_stage_update(self, stage: str) -> None:
        if self.last_stage != 'VENT':
            self.artists[self.last_stage + '_TIMER'].set_text(
                f'{round(-(self.axes[self.last_stage].get_xlim()[0] - 0.1), 1)}s')

        self.axes[stage].set_facecolor(IP_FACE_COLOR)

    def stage_change_update(self, stage: str) -> None:
        if self.last_stage in self.stages:
            self.complete_stage()

        if stage in self.stages:
            self.test_stage_update(stage)

    def plot_update(self, stage: str, x: float, y: float) -> None:
        self.points[stage]['x'].append(-x)
        self.points[stage]['y'].append(y)
        self.artists[stage][0].set_data(self.points[stage]['x'], self.points[stage]['y'])

    def psi_update(self, stage: str, psi: float) -> None:
        a = self.artists[stage + '_TEXT']
        text = f'{round(psi, 4)}psi'
        if text != self.last_text:
            a.set_text(text)
            self.last_text = text

    def timer_update(self, stage: str, x: float) -> None:
        a = self.artists[stage + '_TIMER']
        timer = f't{round(-x)}s'
        if timer != self.last_timer:
            a.set_text(timer)
            self.last_timer = timer

    def testing_update(self, stage: str, x: float, y: float) -> None:
        if stage != 'VENT':

            psi = y
            if stage == 'TEST':
                psi = y - self.last_pressure

                if self.last_stage == 'SETTLE':
                    self.axes['TEST'].set_ylim(self.last_pressure - 0.015, self.last_pressure)

            else:
                self.last_pressure = y

            self.plot_update(stage, x, y)
            self.psi_update(stage, psi)

        self.timer_update(stage, x)
        self.last_stage = stage

    def result_update(self, stage: str) -> None:
        line_color = GRN if stage == 'PASS' else RED

        vent_title = self.artists['VENT_TITLE']
        vent_title.set_color(line_color)
        vent_title.set_text(stage)
        vent_title.set_x(1 - LABEL_X_OFFSET)
        vent_title.set_horizontalalignment('right')

        [self.artists[stg][0].set_color(line_color) for stg in self.stages]

    def update(self, iteration_data):
        stage, x, y = iteration_data

        if stage != self.last_stage:
            self.stage_change_update(stage)

        if stage in self.stages:
            self.testing_update(stage, x, y)

        else:
            self.result_update(stage)


def main(figure):
    fig, animation = setup_chart(figure, data.FakeObj(), data.unit_data)

    return fig, animation
