import tkinter as tk
from dataclasses import dataclass
from functools import partial
from tkinter import font
from typing import *

# from model.resources import APP
from model.resources import COLORS
from model.resources import RESOURCE
from src.base.log import logger
from src.base.general import truncate
from src.model.load import dynamic_import
from src.model.enums import MouseAction
from src.view.base.cell import *
from src.view.base.component import *
from src.view.base.helper import with_enabled
from src.view.base.component import StepProgress

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
        self._update_interval = RESOURCE.cfg('general')['LOG_DISPLAY_UPDATE_INTERVAL_MS']
        self.font = font.nametofont('TkFixedFont')
        self.font.config(size=RESOURCE.cfg('view')['FONTSIZE']['LOGGING'])
        self.vbar = Scrollbar(self)

        bg_ = COLORS.black
        self.text = tk.Text(self, state='disabled', wrap='none', relief='flat', cursor='arrow',
                            fg=APP.V.COLORS.text.normal, bg=bg_,
                            selectbackground=bg_, inactiveselectbackground=bg_,
                            font=self.font, yscrollcommand=self.vbar.set)

        self.vbar['command'] = self.text.yview
        self.vbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._length = 0
        self._max_length = APP.G.LOG_HISTORY_LEN

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
        _colors = APP.V.COLORS.instrument

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
        self.perform_controller_action(self, 'check')

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
        _maj = self._make_font(APP.V.FONTSIZE.INSTRUCTION_MAJOR)
        _min = self._make_font(APP.V.FONTSIZE.INSTRUCTION_MINOR)
        self._notification_interval: int = self.constants['NOTIFICATION_INTERVAL_MS']
        self.major: Label = self._load(Label(self, font=_maj), 'major_widget')
        self.minor: Message = self._load(Message(self, justify='center', font=_min,
                                                 width=int(self.w_co * 0.9)), 'minor_widget')
        self.subs: List[Label] = [self.major, self.minor]
        self.last_settings = '', '', None
        self.disable()

    def set(self, major_text, minor_text, color=None):
        """
        exposed, saves settings and cancels scheduled notification reversion
        """
        self.last_settings = major_text, minor_text, color
        self._set(major_text, minor_text, color)
        self.cancel_scheduled()

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

    def notify(self, major_text, minor_text, color=None):
        """
        set instruction widget per args and revert to last settings after interval from ini
        """
        self.cancel_scheduled()
        self._set(major_text, minor_text, color)
        self.schedule(self._notification_interval, self._revert)


class TestSteps(Cell):
    """
    show test step progress as it happens
    """
    # TODO: this
    step_frames: Dict[str, StepProgress] = dict()

    def make_steps(self, steps: Dict[str, int]) -> None:
        log.info('making steps')
        for i, (name, max_val) in enumerate(steps.items()):
            self.step_frames[name] = widget = StepProgress(self, name, max_val, 66)
            widget.pack(fill=tk.X, expand=0)

    def increment(self, step: str) -> None:
        self.step_frames[step].progress_bar.increment()

    def result_pass(self, step: str) -> None:
        self.step_frames[step].result_pass()

    def result_fail(self, step: str) -> None:
        self.step_frames[step].result_fail()

    def start_progress(self, step: str) -> None:
        self.step_frames[step].start_progress()

    def __post_init__(self):
        self.perform_controller_action(self, 'get_steps')

    def drag_h(self, action: MouseAction) -> Optional[bool]:
        return self.category.cycle(not action.direction)


class Chart(Cell):
    """
    show current or historical test data
    """
    data_iter: Iterator

    def __post_init__(self):
        _bg = COLORS.black
        _dpi = self.parent.screen.dpi

        _import_path = APP.STATION.import_path
        _import_path = ('lighting', 'LL3')
        chart_package = dynamic_import('chart', *_import_path)
        _fake_data_cla = getattr(chart_package, 'FakeData')
        _plot_cla = getattr(chart_package, 'Plot')

        _fake_mn = 938
        self.fake_data = _fake_data_cla(_fake_mn)
        self.interval = 1

        self.plot = _plot_cla(self.fake_data.params,
                              w=self.w_co, h=self.h_co, dpi=_dpi, color=_bg, mn=_fake_mn)
        self.plot.set_background()
        self.chart = self.plot.for_tk(self)
        self.update()

    def _before_show(self) -> None:
        """
        make fake message generator
        """

        def sim_data():
            for msg in self.fake_data.messages:
                yield [msg]

        self.data_iter = sim_data()

    def _on_hide(self):
        """
        stop fake data consumer
        not necessary in production
        """
        self.cancel_scheduled()

    def _on_show(self) -> None:
        """
        plot params-dependent stuff and start updating
        """
        log.info('load_chart called')
        self.plot.init()
        self.update()
        self.schedule(self.interval, self.update_chart_data)
        log.info('chart showing')

    def update_chart(self, msg) -> None:
        """
        call directly from controller
        """
        self.plot(msg)
        self.update()

    def update_chart_data(self):
        """
        get next message from fake message iterator
        and pretend it was received from controller
        """
        try:
            data = next(self.data_iter)

        except StopIteration:
            pass

        else:
            self.update_chart(data)
            self.schedule(self.interval, self.update_chart_data)

    def _before_destroy(self):
        """
        kill plt and plt.fig to prevent tk backend bs on close
        """
        import matplotlib.pyplot as plt

        try:
            self.chart.destroy()
            plt.close(self.plot.fig)

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
