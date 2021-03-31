from typing import *

from framework.model import *
from framework.view.base.placement import *
from framework.view.view import View
from framework.view.widgets.dynamic import *
from framework.view.widgets.history import *
from framework.view.widgets.static import *
from framework.view.base.helper import File

__all__ = [
    'LightingView',
]

log = logger(__name__)

LEFT = TOP = 0
METRICS_W = SIZING.S
TIME_W = SIZING.XS
BUILD_W = SIZING.S
STATS_HEIGHT_RATIO = 1 / 2

_BOTTOM_ROW = SIZING.XXS
_TOP_ROW_H = SIZING.S - _BOTTOM_ROW

_Logo = Pos(LEFT, TOP, SIZING.S, _TOP_ROW_H)
_Title = Pos(_Logo.right, TOP, SIZING.XS, _TOP_ROW_H / 2)
_Mode = Pos(_Logo.right, _Title.bottom, _Title.w, _Title.h)
_Metrics = Pos(1 - METRICS_W, TOP, METRICS_W, _TOP_ROW_H)
_Instruction = Pos(_Logo.w + _Title.w, TOP, 1 - _Logo.w - _Title.w - _Metrics.w, _TOP_ROW_H)

_Stats = Pos(LEFT, _TOP_ROW_H, SIZING.S, SIZING.L * STATS_HEIGHT_RATIO)

_ModelButton = Pos(LEFT, _Stats.bottom, _Stats.w * .45, SIZING.XXS * 1.5)
_HistoryRecencyButton = Pos(_ModelButton.right, _Stats.bottom, _Stats.w * .2, _ModelButton.h)
_PassFailButton = Pos(_HistoryRecencyButton.right, _Stats.bottom, _Stats.w * .2, _ModelButton.h)
_HistoryLengthButton = Pos(_PassFailButton.right, _Stats.bottom, _Stats.w * .15, _ModelButton.h)

_History = Pos(LEFT, _ModelButton.bottom, _Stats.w, (SIZING.L - _Stats.h) - _ModelButton.h)

_RIGHT_MAIN = Pos(_Stats.right, _TOP_ROW_H, 1 - _Stats.w, SIZING.L)

_Instruments = Pos(LEFT, _RIGHT_MAIN.bottom, _Stats.w, _BOTTOM_ROW)
_Time = Pos(1 - TIME_W, _RIGHT_MAIN.bottom, TIME_W, _BOTTOM_ROW)
_Build = Pos(1 - BUILD_W - TIME_W, _RIGHT_MAIN.bottom, BUILD_W, _BOTTOM_ROW)
_StatusBar = Pos(_Stats.right, _RIGHT_MAIN.bottom, _RIGHT_MAIN.w - BUILD_W - TIME_W, _BOTTOM_ROW)


class LightingView(View):
    widgets = [
        # # top
        # left
        WidgetPosition(Logo, _Logo),

        # right
        WidgetPosition(TestTitle, _Title),
        WidgetPosition(Mode, _Mode),
        WidgetPosition(Instruction, _Instruction),
        WidgetPosition(Metrics, _Metrics),

        # # middle
        # left
        WidgetPosition(TestSteps, _Stats),

        WidgetPosition(HistoryPartNumber, _ModelButton),
        WidgetPosition(HistoryRecency, _HistoryRecencyButton),
        WidgetPosition(HistoryPassFail, _PassFailButton),
        WidgetPosition(HistoryLength, _HistoryLengthButton),

        WidgetPosition(History, _History),

        # right
        WidgetPosition(Logging, _RIGHT_MAIN),
        WidgetPosition(Chart, _RIGHT_MAIN),

        # # bottom
        # left
        WidgetPosition(Instruments, _Instruments),

        # right
        WidgetPosition(TitleBar, _StatusBar),
        WidgetPosition(Build, _Build),
        WidgetPosition(Time, _Time),
    ]
    categories = {
        # _LEFT_MAIN.tuple: Category('left_side'),
        _RIGHT_MAIN.tuple: Category('right_side'),
    }

    def log(self) -> Optional[bool]:
        """
        swap showing log and chart widgets
        """
        log.info('Window.log() has been called')
        return self.categories['right_side'].cycle()

    def test_one(self) -> None:
        self.perform_controller_action('history', 'all')

    def test_two(self) -> None:
        self.perform_controller_action('history', 'new')

    def ask_save(self) -> None:
        filename = File.open('Select a file to open...', r'C:\Users\pcreagan\Desktop', File.XLS, File.CSV,
                             File.ALL)
        log.info(f'File.open() -> {filename}')

    def ask_open(self) -> None:
        filename = File.save('Select a file to save...', r'C:\Users\pcreagan\Desktop', File.XLS, File.CSV)
        log.info(f'File.save() -> {filename}')
