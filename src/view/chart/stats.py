# pylint: disable=import-error
from matplotlib.patches import ConnectionPatch
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pandas import read_excel, DataFrame
# pylint: enable=import-error
from sample_data import fake_data
# from leak_tester import Leak_Test, Leak_Tester
from time import time, perf_counter
from csv import reader

FACE_COLOR = '0.07'
DPI = 96
FONT_NAME = 'Roboto'
NORMAL_TEXT_COLOR = 'white'
PIE_EXPLODE = 0.1


class Stats:
    # def __init__(self, fp: str):
    #     self.fp = fp

    def simulate(self):
        self.pie_types = ['fail', 'pass', 'aborted']
        self.pie_ratios = [.08, .88, .04]
        self.bar_types = ['leak', 'low pressure',
                          'gross leak', 'high pressure']
        self.bar_ratios = [.06, .54, .07, .33]

    # def read_results_file(self):
    #     sheet = read_excel(self.fp)
    #     self.sheet = sheet.values.tolist()
    #     print(self.sheet)


# stats = Stats(r'Consolidated Pressure Test Results.csv')
# stats.read_results_file()


# def test_chart(test: Leak_Test):

#     plt.close('all')
#     plt.style.use('seaborn-darkgrid')
#     plt.figure(figsize=(480/DPI, 480/DPI), dpi=DPI)

#     plt.subplots_adjust(top=1, bottom=0, right=1, left=0,
#                         hspace=0, wspace=0)
#     plt.clf()
#     ax = plt.gca()
#     ax.set_facecolor(FACE_COLOR)
#     ax.set_ylabel('')
#     ax.set_xlabel('')
#     ax.set_yticklabels([])
#     ax.set_xticklabels([])
#     ax.yaxis.set_major_locator(plt.NullLocator())
#     ax.xaxis.set_major_locator(plt.NullLocator())

#     ax.plot(
#         test.chart_df['measurement'],
#         test.chart_df['values'],
#         marker='',
#         color=test.plot_color,
#         linewidth=4,
#         alpha=0.7
#     )
#     ax.set_xlim(0, test.xmax)
#     ax.set_ylim(test.ymin, test.ymax)

#     plt.margins(0, 0)
#     plt.padding = (0, 0)
#     plt.tight_layout(pad=0)

#     dut_blurb = f'''\
# MN{test.mn_string} SN{test.sn}
# uid: {test.uid}
# date: {test.consolidated_list[0]}
# time: {test.consolidated_list[1]}\
# '''
#     plt.figtext(
#         test.prog_blurb_x, 0.975,
#         dut_blurb,
#         va='top',
#         ma='left',
#         color=NORMAL_TEXT_COLOR,
#         fontname=FONT_NAME,
#         style='normal',
#         fontweight='bold',
#         fontsize='xx-large'
#     )

#     program_blurb = f'''\
# PROGRAM {test.test_prog_number}: "{test.test_prog}"
# cavity volume: {test.volume}cc
# test range: {test.ymin}-{test.ymax}psi
# max decay: {test.decay_limit}psi\
# '''
#     plt.figtext(test.prog_blurb_x, 0.05,
#                 program_blurb,
#                 ma='left',
#                 color=NORMAL_TEXT_COLOR,
#                 fontname=FONT_NAME,
#                 style='normal',
#                 fontweight='normal',
#                 fontsize='x-large')

#     plt.figtext(0.99, 0.975,
#                 test.result_string,
#                 ha='right',
#                 va='top',
#                 ma='right',
#                 color=test.plot_color,
#                 fontname=FONT_NAME,
#                 style='normal',
#                 fontweight='bold',
#                 fontsize='xx-large')

#     # plt.draw()
#     return plt


def chart_example():
    lt = Leak_Tester()
    lt.test_prog = 'DRAGON'
    lt.mn = '00918'
    lt.test_pressure = 2.5
    lt.pressure_max = 0.65
    lt.pressure_min = 0.5
    lt.fast_fill_timer = 2.0
    lt.fill_timer = 9.0
    lt.settle_timer = 20.0
    lt.test_timer = 30.0
    lt.vent_timer = 14.0
    lt.increase_limit = 0.015
    lt.decay_limit = 0.015
    lt.test_volume = 1380.0
    lt.test_type = 0
    lt.test_program = 14
    lt.calc_chart()

    test = Leak_Test(lt, str(round(time())), 'UIDUIDUIDUID')
    for meas in fake_data:
        test.add_row(*list(map(str, meas)))
    test.finish_test()

    return test_chart(test)


def pass_fail_chart(stats: Stats):
    plt.close('all')
    fig = plt.figure(figsize=(256 / DPI, 256 / DPI), dpi=DPI)
    fig.subplots_adjust(wspace=0)
    fig.set_facecolor(FACE_COLOR)

    pie_labels = [f'{round(pcnt * 100, 2)}% {label.lower()}' for pcnt,
                                                                 label in
                  zip(stats.pie_ratios, stats.pie_types)]
    explode = [PIE_EXPLODE] * len(pie_labels)
    angle = -180 * stats.pie_ratios[0]

    pie_colors = ['red', 'green', 'grey', ]

    ax = plt.gca()
    ax.pie(
        stats.pie_ratios,
        startangle=angle,
        labels=pie_labels,
        # labeldistance=0.6,
        explode=explode,
        colors=pie_colors,
        textprops={
            'weight': 'bold',
            'color': NORMAL_TEXT_COLOR,
            'fontname': FONT_NAME,
            'fontsize': 'x-large'
        }
    )
    ax.axis('equal')
    plt.tight_layout(pad=0)
    plt.draw()
    return plt


class Stats:
    # def __init__(self, fp: str):
    #     self.fp = fp

    def simulate(self):
        self.pie_types = ['fail', 'pass', 'aborted']
        self.pie_ratios = [.08, .88, .04]
        self.bar_types = ['leak', 'low pressure',
                          'gross leak', 'high pressure']
        self.bar_ratios = [.06, .54, .07, .33]


def failure_types_chart(stats: Stats):
    plt.close('all')
    fig = plt.figure(figsize=(256 / DPI, 128 / DPI), dpi=DPI)
    fig.subplots_adjust(wspace=0)
    fig.set_facecolor(FACE_COLOR)
    bottom = 0
    width = .05
    ax = plt.gca()
    for j, mode in enumerate(stats.bar_types):
        height = stats.bar_ratios[j]
        if height > 0:
            ax.bar(0,
                   height,
                   width,
                   bottom=bottom,
                   color=[0.7 - (0.1 * j), 0, 0],
                   # edgecolor='white',
                   )
            patches_height = ax.patches[j].get_height()
            pcnt_string = "%d%%" % (patches_height * 100)
            label = f'{pcnt_string} {mode.lower()}'
            ypos = bottom + patches_height
            bottom += height
            ax.text(
                width / 2,
                ypos,
                label,
                ha='left',
                va='top',
                color=NORMAL_TEXT_COLOR,
                weight='bold',
                fontname=FONT_NAME,
            )

    ax.axis('off')
    ax.xaxis.set_major_locator(plt.NullLocator())
    ax.yaxis.set_major_locator(plt.NullLocator())
    # ax.set_ylim(.5, 1)
    ax.set_xlim(0, width * 1.5)

    # plt.tight_layout(pad=0)
    plt.tight_layout()
    plt.draw()
    return plt


def nested_pie():
    plt.close('all')
    fig = plt.figure(figsize=(512 / DPI, 512 / DPI), dpi=DPI)
    fig.subplots_adjust(wspace=0)
    fig.set_facecolor(FACE_COLOR)

    size = 0.2
    p_f_values = np.array([0.91, 0.09])
    fail_cat = np.array([60., 32., 40., 10.])

    outer_colors = [[0.7 - (0.1 * j)] * 3
                    for j in range(len(fail_cat))]
    inner_colors = ['green', 'red', ]

    ax = plt.gca()
    ax.set(aspect="equal")

    for vals, colors, rad, sz in zip([fail_cat, p_f_values],
                                     [outer_colors, inner_colors],
                                     [1, 1 - size],
                                     [size, 1 - size], ):
        ax.pie(
            vals,
            radius=rad,
            colors=colors,
            wedgeprops=dict(
                width=sz,
                edgecolor='white'
            )
        )

    plt.tight_layout(pad=0)
    return plt


if __name__ == '__main__':
    # plot = test_chart_test()
    # plot.show(block=True)
    stats = Stats()
    stats.simulate()
    ti = perf_counter()
    plot = pass_fail_chart(stats)
    tf = perf_counter()
    print(tf - ti)
    plot.show(block=True)
    ti = perf_counter()
    plot = failure_types_chart(stats)
    tf = perf_counter()
    print(tf - ti)
    # plot = nested_pie()
    plot.show(block=True)
