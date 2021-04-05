import tkinter as tk
from dataclasses import dataclass
from functools import partial
from operator import attrgetter
from tkinter import font
from typing import *

from src.base.general import truncate
from src.base.log import logger
from src.model.db import connect
from src.model.db.schema import LightingDUT
from src.model.db.schema import LightingStation3Iteration
from src.model.db.schema import LightingStation3LightMeasurement
from src.model.db.schema import LightingStation3Param
from src.model.db.schema import LightingStation3ResultRow
from src.model.enums import MouseAction
from src.model.load import dynamic_import
from src.model.resources import APP
from src.model.resources import COLORS
from src.model.vc_messages import InstructionMessage
from src.model.vc_messages import NotificationMessage
from src.model.vc_messages import StepFinishMessage
from src.model.vc_messages import StepMinorTextMessage
from src.model.vc_messages import StepProgressMessage
from src.model.vc_messages import StepsInitMessage
from src.model.vc_messages import StepStartMessage
from src.stations.lighting.station3.model import Station3ChartParamsModel
from src.view.base.cell import *
from src.view.base.component import *
from src.view.base.component import StepProgress
from src.view.base.decorators import subscribe
from src.view.base.helper import with_enabled
from src.view.chart.base import Root

__all__ = [
    'TestSteps',
    'Instruments',
    'Instruction',
    'Logging',
    'Chart',
    'WIDGET',
    'WIDGET_TYPE',
]

log = logger(__name__)


class Logging(Cell):
    """
    shows logger console output in GUI for debug
    """

    def __post_init__(self):
        self._update_interval = APP.G['LOG_DISPLAY_UPDATE_INTERVAL_MS']
        self.font = font.nametofont('TkFixedFont')
        self.font.config(size=APP.V['FONTSIZE']['LOGGING'])
        self.vbar = Scrollbar(self)

        bg_ = COLORS.black
        self.text = tk.Text(self, state='disabled', wrap='none', relief='flat', cursor='arrow',
                            fg=COLORS.white, bg=bg_,
                            selectbackground=bg_, inactiveselectbackground=bg_,
                            font=self.font, yscrollcommand=self.vbar.set)

        self.vbar['command'] = self.text.yview
        self.vbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._length = 0
        self._max_length = APP.G['LOG_HISTORY_LEN']

    def _on_show(self):
        """
        determine max line length and return function for processing
        start update on interval from ini
        """
        limit = int(self.text.winfo_width() / self.font.measure('m')) - 1
        self._truncate = partial(truncate, limit=limit)
        self.schedule(self._update_interval, self.update_log)

    def _replace_content(self, lines) -> None:
        """
        write log entries to text widget
        """

        # add new lines
        self.text.insert('end', '\n' + '\n'.join(map(self._truncate, lines)))
        self._length += len(lines)

        # remove stale lines if any
        stale = max(0, self._length - self._max_length)
        if stale:
            self.text.delete(1.0, float(stale + 1))
            self._length -= stale

        # scroll to end
        self.text.see('end')

    def update_log(self) -> None:
        """
        if new log entries, retrieve all in logger deque (thread-safe)
        truncate lines and replace text
        repeats on interval from ini
        """
        if self.parent.log_deque.new:
            with_enabled(self.text)(self._replace_content)(self.parent.log_deque.get())

        self.schedule(self._update_interval, self.update_log)


class Instruments(Cell):
    """
    shows station's instruments and their status
    on click, requests TE check from controller
    """

    @dataclass
    class Instrument:
        """
        one instrument status label
        """
        widget: Label
        state: str
        _colors = {
            'checking': COLORS.white,
            'bad': COLORS.red,
            'good': COLORS.green,
        }

        def update(self, state: str) -> None:
            """
            set state for one instrument label
            """
            self.widget.color(fg=getattr(self._colors, state, 'bad'))
            self.state = state

        def __bool__(self) -> bool:
            """
            return whether instrument has been checked
            useful for accumulators
            """
            return self.state != 'checking'

    def __post_init__(self):
        _clickable = bool(len(APP.STATION.instruments))
        _instruments = [inst for inst in APP.STATION.instruments]
        _spot = 1 / len(_instruments)
        _instruments.sort()
        self.instruments: Dict[str, 'Instruments.Instrument'] = dict()
        for i, s in enumerate(_instruments):
            label = Label(self, anchor="center", font=self.font,
                          fg=COLORS.white,
                          bg=COLORS.medium_grey)
            label.text(getattr(APP.INSTRUMENTS, s)['display_name'])
            self.instruments[s] = self.Instrument(
                widget=label.place(x=_spot * i, y=0, height=1, width=_spot), state='checking'
            )

    def get_fresh_data(self):
        """
        ask controller for test equipment status
        """
        self.disable()
        [v.update('checking') for v in self.instruments.values()]
        # self.perform_controller_action(self, 'check')

    def check_all_done(self) -> None:
        """
        if all instruments have been updated, change widget appearance
        """
        if all(self.instruments.values()):
            self.fresh_data()

    def update_instrument(self, name, state):
        """
        if state has changed, updates one instrument label
        if all instruments have been updated, enables widget
        """
        if self.instruments[name].state != state:
            self.instruments[name].update(state)
            self.check_all_done()

    def _on_show(self):
        self.get_fresh_data()

    def double_click(self, evt: tk.EventType):
        _ = evt
        self.get_fresh_data()


class Instruction(Cell):
    """
    used to provide string updates and prompts to user
    major and minor sub_widgets are handled together
    """

    last_settings: Tuple[str, str, Any]

    def initial_state(self) -> None:
        self.set('-', '')

    def __post_init__(self):
        _maj = self._make_font(APP.V['FONTSIZE']['INSTRUCTION_MAJOR'])
        _min = self._make_font(APP.V['FONTSIZE']['INSTRUCTION_MINOR'])
        self._notification_interval: int = self.constants['NOTIFICATION_INTERVAL_MS']
        self.major: Label = self._load(Label(self, font=_maj), 'major_widget')
        self.minor: Message = self._load(Message(self, justify='center', font=_min,
                                                 width=int(self.w_co * 0.9)), 'minor_widget')
        self.subs: List[Label] = [self.major, self.minor]
        self.last_settings = '', '', None
        self.disable()

    def _set(self, major, minor, color) -> None:
        """
        configures widget components based on args
        """
        if major or minor:
            [o.forget() for o in self.subs]
            if major and minor:
                [o.cfg(anchor=a).text(s).pack() for o, a, s in zip(self.subs, ['s', 'n'], [major, minor])]
            elif major:
                self.major.cfg(anchor='center').text(major).pack()
            elif minor:
                self.minor.cfg(anchor='center').text(minor).pack()
        if color is not None:
            [widget.color(fg=color) for widget in [self.major, self.minor]]

    def _revert(self) -> None:
        """
        return to last settings after a notification expires
        """
        self._set(*self.last_settings)

    @subscribe(InstructionMessage)
    def set(self, major, minor, color=None):
        """
        exposed, saves settings and cancels scheduled notification reversion
        """
        self.last_settings = major, minor, color
        self._set(major, minor, color)
        self.cancel_scheduled()

    @subscribe(NotificationMessage)
    def notify(self, major, minor, color=None):
        """
        set instruction widget per args and revert to last settings after interval from ini
        """
        self.cancel_scheduled()
        self._set(major, minor, color)
        self.schedule(self._notification_interval, self._revert)


class TestSteps(Cell):
    """
    show test step progress as it happens
    """
    step_frames: Dict[str, StepProgress] = dict()

    def __post_init__(self):
        pass

    @subscribe(StepsInitMessage)
    def make_steps(self, steps: List[str]) -> None:
        log.info('making steps')
        [widget.pack_forget() for widget in self.step_frames.values()]
        [widget.destroy() for widget in self.step_frames.values()]
        self.step_frames.clear()
        for i, name in enumerate(steps):
            self.step_frames[name] = widget = StepProgress(self, name, 66)
            widget.pack(fill=tk.X, expand=0)
            print(f'packed step -> {name}')

    @subscribe(StepStartMessage)
    def start_progress(self, step: str, minor_text: Optional[str],
                       max_val: Optional[Union[int, float]]) -> None:
        self.step_frames[step].start_progress(minor_text, max_val)

    @subscribe(StepMinorTextMessage)
    def set_minor_text(self, step: str, minor_text: str) -> None:
        self.step_frames[step].minor_text(minor_text)

    @subscribe(StepProgressMessage)
    def set_progress(self, step: str, value: Union[int, float]) -> None:
        self.step_frames[step].set_progress(value)

    @subscribe(StepFinishMessage)
    def end_progress(self, step: str, success: Optional[bool]) -> None:
        self.step_frames[step].end_progress(success)

    def drag_h(self, action: MouseAction) -> Optional[bool]:
        return self.category.cycle(not action.direction)


class Chart(Cell):
    """
    show current or historical test data
    """
    _bg = COLORS.black

    def __post_init__(self):
        _plot_cla: Type[Root] = getattr(dynamic_import('chart', *APP.STATION.import_path), 'Plot')

        with connect(echo_sql=False)(expire=False) as session:
            param = LightingStation3Param.get(session, '918 brighter')
            iteration: LightingStation3Iteration = session.query(LightingStation3Iteration).first()
            dut: LightingDUT = iteration.dut

            params = Station3ChartParamsModel(
                param_id=param.id, mn=dut.mn, rows=list(sorted(param.rows, key=attrgetter('row_num')))
            )

        self._plot = _plot_cla(params, w=self.w_co, h=self.h_co,
                               dpi=self.parent.screen.dpi, color=self._bg)

    def _before_show(self) -> None:
        pass

    def _on_hide(self) -> None:
        pass

    def _on_show(self) -> None:
        self._plot.set_background()
        self._chart = self._plot.for_tk(self)
        self._chart.update()
        self._plot.init()
        self._chart.update()
        self.update()

    @subscribe(LightingStation3LightMeasurement,
               LightingStation3Iteration,
               LightingDUT,
               LightingStation3ResultRow, )
    def update_chart_data(self, message):
        """
        get next message from fake message iterator
        and pretend it was received from controller
        """
        self._plot(message)
        self._chart.update()

    def _before_destroy(self):
        """
        kill plt and plt.fig to prevent tk backend bs on close
        """
        import matplotlib.pyplot as plt

        try:
            self._chart.destroy()
            plt.close(self._plot.fig)

        except AttributeError:
            pass

        plt.clf()


WIDGET = Union[
    TestSteps,
    Instruments,
    Instruction,
    Logging,
    Chart,
]

WIDGET_TYPE = Type[WIDGET]
