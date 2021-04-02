import collections
import datetime
import time
import tkinter as tk
from dataclasses import dataclass
from functools import partial
from typing import *

from src.base.log import logger
from src.view.base.cell import *
from src.view.base.component import Label
from src.view.base.helper import with_enabled
from src.view.base.image_funcs import make_circle_glyph
from src.view.base.component import Scrollbar

__all__ = [
    'Mode',
    'Metrics',
    'History',
    'HistoryPartNumber',
    'HistoryPassFail',
    'HistoryLength',
    'HistoryRecency',
]


log = logger(__name__)

_RECORD = Dict[str, [int, bool, datetime.datetime, str, str]]
_RECORDS = List[_RECORD]
_RECORD_DICT = Dict[int, _RECORD]
_RECORD_ID_SET = Set[int]


class Mode(Cell):
    """
    acts as a button, toggling between test and rework modes
    """

    @dataclass
    class Setting:
        """
        one instance of Setting corresponds to one button state
        """
        display_s: str
        config_d: Dict[str, Any]
        next: Optional[str] = None

    state: str
    next_state: str
    checking_str = 'checking'
    testing_str = 'testing'
    rework_str = 'rework'

    def __post_init__(self):
        self.object: Label = self._load(Label(self))
        self._settings: Dict[str, 'Mode.Setting'] = {s: self.Setting(
            self.constants['strings'][s], dict(fg=getattr(APP.V.COLORS.mode, s)), next=_next
        ) for s, _next in zip([self.checking_str, self.testing_str, self.rework_str],
                              [None, self.rework_str, self.testing_str])}
        self._set(self.rework_str)

    def _set(self, name: str) -> None:
        """
        change indicator appearance per settings[name]
        """
        self.state = name
        setting = self._settings[name]
        self.next_state = cast(str, setting.next)
        self.object.text(setting.display_s).config(**setting.config_d)

    def set(self, name: str):
        """
        exposed method
        shows change with fresh_data()
        """
        self._set(name)
        self.fresh_data()

    def handle_response(self, msg) -> None:
        """
        do something when controller returns mode change request
        """
        self.set(self.next_state if msg.is_success else self.state)
        # if msg.is_success:
        #     if self.state == self.testing_str:
        # self.parent_widget(History).enable_double_clicking()

    def get_fresh_data(self):
        """
        wait for controller to update mode with widget disabled
        ask controller to toggle mode
        """
        self.disable()

        # if widget := self.parent_widget(History, fail_silently=True):
        # History may not be initialized at this point
        # widget.disable_double_clicking()

        self.object.config(**self._settings[self.checking_str].config_d)
        self.perform_controller_action(self, 'change', self.next_state, callback=self.handle_response)

    def _on_show(self):
        self.get_fresh_data()

    def double_click(self, evt: tk.EventType):
        _ = evt
        self.get_fresh_data()


class Metrics(Cell):
    """
    shows pass/fail statistics for one station
    """
    _numbers: Tuple[int, int, int, int]

    def __post_init__(self):
        names = ['percent_text', 'fail_text', 'pass_text', 'label', ]
        self._names, spot = names[:-1], 1 / len(names)
        self._last_settings = dict()

        pass_pct = self.constants['pct'] == 'pass'
        self._make_pct = self._pass_pct if pass_pct else self._fail_pct
        self._normal_colors = tuple([getattr(APP.V.COLORS.metrics, name) for name in names][:-1])
        self._checking_colors = tuple([APP.V.COLORS.instrument.checking] * 3)

        [[self._load(Label(self, anchor='center',
                           fg=getattr(APP.V.COLORS.metrics, name), bg=APP.V.COLORS.background.lighter),
                     f'{name}_{row}', x=spot * column, y=.5 * row, height=.5, width=spot
                     ) for column, name in enumerate(names)] for row in range(2)]

        [getattr(self, f'label_{row}').text(f) for row, f in zip(range(2), ['h', 'd'])]
        [self._set_row('text', ('-', '-', '-%'), i) for i in range(2)]
        self._numbers = -1, -1, -1, -1

    def double_click(self, evt: tk.EventType):
        _ = evt
        self.disable()
        [self._set_row('color', self._checking_colors, row) for row in range(2)]
        self.perform_controller_action('history', 'all')

    @staticmethod
    def _fail_pct(p: int, f: int) -> str:
        """
        compute failure percentage
        if pass+fail == 0, return 0%
        """
        if (f + p) == 0:
            return '-%'
        return f'{round((f / (f + p)) * 100)}%'

    @staticmethod
    def _pass_pct(p: int, f: int) -> str:
        """
        compute pass percentage
        if pass+fail == 0, return 0%
        """
        if (f + p) == 0:
            return '-%'
        return f'{round((p / (f + p)) * 100)}%'

    def _set_row(self, f: str, args: tuple, row: int) -> None:
        """
        set all label values in a row, ex. pass/hour, fail/hour, p/f/hour
        or set all colors in a row, same ordering
        does not perform tk action if args == last setting for that function and row
        """
        k = f, row
        _last = self._last_settings.get(k, None)
        if _last:
            if _last == args:
                return
        [getattr(getattr(self, f'{name}_{row}'), f)(v) for name, v in zip(self._names, args)]
        self._last_settings[k] = args

    def set_numbers(self, fail_hour: int, pass_hour: int, fail_day: int, pass_day: int) -> None:
        """
        if stats have changed since last update, updates text display lines
        """
        self.disable()
        _numbers = fail_hour, pass_hour, fail_day, pass_day
        if _numbers != self._numbers:
            self._numbers = _numbers
            _rows = self._numbers[:2], self._numbers[2:]
            [self._set_row('text', (p, f, self._make_pct(p, f)), i) for i, (f, p) in enumerate(_rows)]
            [self._set_row('color', self._normal_colors, row) for row in range(2)]
        self.fresh_data()


class History(Cell):
    """
    show MN and SN of last tested units on this station
    """
    # ? https://stackoverflow.com/a/31766128
    # ? https://www.tutorialspoint.com/python/tk_listbox.htm

    _dt_ft: str = APP.V.widget_constants['Time']['DT_FORMAT']
    _pad: int = 2
    _last_results_fresh: bool

    def __post_init__(self):
        # initialize state variables
        self.configure(bg=APP.V.COLORS.background.darker)
        self._create_kws = dict(pady=self._pad)
        self._kws = dict(
            compound=tk.LEFT, relief='flat', overrelief='flat',
            disabledforeground=APP.V.COLORS.text.normal, state='disabled',
            fg=APP.V.COLORS.text.normal, bg=APP.V.COLORS.background.lighter,
            bd=0,
        )
        self._pass_ids = set()
        self._fail_ids = set()
        self._day_ids = set()
        self._day_sns = dict()
        self._hour_ids = set()
        self._model_ids = collections.defaultdict(set)
        self._lines = dict()
        self._displayed_ids = set()
        self.__last_results = set()
        self._elisions = dict()
        self._buttons = list()
        self._p_f_dict = {
            HistoryPassFail.pass_string: self._pass_ids,
            HistoryPassFail.fail_string: self._fail_ids
        }
        self._len_f = HistoryLength.initial_setting
        self._pf_f = HistoryPassFail.initial_setting
        self._model_setting = HistoryPartNumber.initial_setting
        self._recency_f = HistoryRecency.initial_setting
        self._last_results_fresh = True
        self._current_button_width = None
        self.scrolled_width = None
        self._midnight = datetime.datetime.combine(datetime.date.today(), datetime.datetime.min.time())

        self.history_frame = tk.Frame(self)
        self.vbar = Scrollbar(self)

        # make text field
        bg_ = APP.V.COLORS.background.darker
        self.field = tk.Text(
            self, state='disabled', wrap='char', relief='flat', cursor='arrow',
            fg=APP.V.COLORS.text.normal, bg=bg_, selectbackground=bg_, inactiveselectbackground=bg_,
            yscrollcommand=self.vbar.set, pady=0, padx=0,
        )
        self.vbar['command'] = self.field.yview

        self.pack_history(True)
        self.history_frame.pack(fill=tk.BOTH, expand=1)

        # noinspection SpellCheckingInspection
        self._h = self.font.metrics('linespace')

        # make pass/fail glyphs
        _ts = [(0, 0, 0)] + [self.constants['glyph'][k]['color'] for k in ('pass', 'fail')]
        self._glyphs = {k: self._make_image(make_circle_glyph(120, .5, c), (self._h, self._h)) for k, c in
                        zip([None, True, False], _ts)}
        self.enable()
        self.last_button_selected = None

    def _button_selected(self, record: _RECORD, button: tk.Button) -> None:
        """
        called when an entry is double-clicked
        """
        if self.last_button_selected:
            try:
                self.last_button_selected.configure(bg=APP.V.COLORS.background.lighter)
            except tk.TclError:
                # last button can be gone before it's reverted
                pass

        button.configure(bg=APP.V.COLORS.background.darker)
        self.last_button_selected = button
        log.info(f'button {record["id"]} selected')

    def _make_entry(self, record: _RECORD) -> tk.Button:
        if self._current_button_width:
            self._kws['width'] = self._current_button_width

        button = tk.Button(
            self, **self._kws, image=self._glyphs[record["pf"]],
            text=f'    {record["sn"]} - {record["dt"].strftime(self._dt_ft)}',
        )
        button['command'] = partial(self._button_selected, record=record, button=button)
        self._buttons.append(button)
        return button

    def add_record(self, record: _RECORD) -> None:
        """
        add one record to the appropriate categories
        """
        dt_ = record['dt']

        # happened today
        if dt_ > self._midnight:
            id_ = record['id']
            sn_ = record['sn']

            self._day_ids.add(id_)
            self._lines[id_] = record

            # happened in the last hour
            # _timestamp = dt_ + datetime.timedelta(hours=1)
            # TODO remove this vvv
            _timestamp = dt_ + datetime.timedelta(minutes=15)
            _now = datetime.datetime.now()
            if _timestamp > _now:
                self._hour_ids.add(id_)
                _timestamp -= _now
                self.after(int(_timestamp.total_seconds() * 1000), self.remove_from_hour, id_)

            # passed or failed
            (self._pass_ids if record['pf'] else self._fail_ids).add(id_)

            # categorize by model number
            self._model_ids[record['mn']].add(id_)

            # most recent result for this sn
            v = self._day_sns.setdefault(sn_, (id_, dt_))
            if v[1] < dt_:
                self._day_sns[sn_] = v
                self._last_results_fresh = True

            # create and tag visible record representation
            self.field.window_create(1.0, window=self._make_entry(record), **self._create_kws)
            self.field.tag_add(str(record['id']), 1.0)

    def _last_results(self) -> _RECORD_ID_SET:
        """
        extract the record ids from the most recent results dict
        """
        if self._last_results_fresh:
            self.__last_results = set([v[0] for v in self._day_sns.values()])
            self._last_results_fresh = False
        return self.__last_results

    def filter_predicate(self, cls) -> bool:
        """
        determine whether to apply a filter from the button widget's class attributes
        """
        return getattr(self, cls._history_attr) != cls.initial_setting

    def filter_for_display(self) -> _RECORD_ID_SET:
        """
        use set intersection to find units that satisfy applicable filters
        """
        filters = list()
        _filter_predicate = self.filter_predicate

        if _filter_predicate(HistoryLength):
            filters.append(self._hour_ids)
        if _filter_predicate(HistoryPassFail):
            filters.append(self._p_f_dict[self._pf_f])
        if _filter_predicate(HistoryPartNumber):
            filters.append(self._model_ids[self._model_setting])
        if _filter_predicate(HistoryRecency):
            filters.append(self._last_results())

        return self._day_ids.intersection(*filters)

    def update_other_widgets(self) -> None:
        """
        update the available selections for the four history select buttons
        update the numbers on the metrics widget in the top right
        """
        self.parent_widget(HistoryPartNumber).set_options(list(self._model_ids.keys()))
        self.parent_widget(HistoryPassFail).set_options([s for s, o in self._p_f_dict.items() if o])
        self.parent_widget(HistoryLength).set_options(self._hour_ids)
        self.parent_widget(HistoryRecency).set_options(self._last_results() != self._day_ids)

        hr_ = self._hour_ids
        self.parent_widget(Metrics).set_numbers(
            fail_day=len(self._fail_ids), pass_day=len(self._pass_ids),
            fail_hour=len(self._fail_ids.intersection(hr_)),
            pass_hour=len(self._pass_ids.intersection(hr_)),
        )

    def button_size(self) -> None:
        for button in self._buttons:
            try:
                button.configure(width=self._current_button_width)
            except Exception as e:
                log.warning(str(e))

    def change_elision(self, _ids: _RECORD_ID_SET) -> None:
        for name in self._day_ids:
            do_elide = name not in _ids
            _last = self._elisions.setdefault(name, None)
            if _last is None or (do_elide ^ _last):
                self.field.tag_configure(str(name), elide=do_elide)
                self._elisions[name] = do_elide
                self.update()

    def pack_forget_widget(self, widget) -> None:
        _ = self
        try:
            widget.pack_forget()
        except Exception as e:
            log.warning(str(e))

    def pack_history(self, scrollable: bool) -> None:
        """
        forget appropriate widget(s)
        pack field or field and vbar
        """
        self.pack_forget_widget(self.field)

        if scrollable:
            self.vbar.pack(in_=self.history_frame, side=tk.LEFT, fill=tk.Y)
            self.field.pack(in_=self.history_frame, side=tk.RIGHT, fill=tk.BOTH, expand=1)

        else:
            self.pack_forget_widget(self.vbar)
            self.field.pack(in_=self.history_frame, fill=tk.BOTH, expand=1)

        self._current_button_width = self.scrolled_width if scrollable else self.width
        self._kws['width'] = cast(int, self._current_button_width)
        self.vbar_packed = scrollable
        self.button_size()

    def _vbar_visibility(self) -> None:
        _conditions = [self.field.yview() == (0., 1.), self.vbar.winfo_ismapped()]

        if all(_conditions):
            self.pack_history(False)

        elif not any(_conditions):
            self.pack_history(True)

    def filter_and_update(self) -> None:
        """
        filter with selections, sort by date, update widget with button(s), schedule update
        """
        _new_ids = self.filter_for_display()
        self.update_other_widgets()
        self.change_elision(_new_ids)
        self._vbar_visibility()

    def _initialize_history(self, lines: _RECORDS) -> None:
        """
        bulk process test history records
        """

        # remove any existing records
        # delete until end-1 to avoid inserting a newline at the end of the field
        self.field.delete('1.0', 'end-1c')

        # tags aren't garbage collected over the whole life of the application
        # so they need to be explicitly destroyed
        [self.field.tag_delete(name) for name in self.field.tag_names() if name != 'sel']

        # clear state
        self._pass_ids.clear()
        self._fail_ids.clear()
        self._day_ids.clear()
        self._hour_ids.clear()
        self._model_ids.clear()
        self._lines.clear()
        self._displayed_ids.clear()
        self._day_sns.clear()
        self._buttons.clear()
        self._elisions.clear()
        self._midnight = datetime.datetime.combine(datetime.date.today(), datetime.datetime.min.time())

        # make sub lists of record ids by category
        list(map(self.add_record, lines))

        # set callback to replace contents at next midnight
        _timestamp = (datetime.timedelta(days=1, seconds=2) + self._midnight) - datetime.datetime.now()
        _next_full_update = int(_timestamp.total_seconds() * 1000)
        self.parent.after(_next_full_update, self.perform_controller_action, 'history', 'all')

    def change_contents(self, f: Callable, *arg) -> None:
        """
        perform an operation one one fresh or stale record
        """
        self.disable()
        _prev_state, self.field['state'] = self.field['state'], 'normal'

        try:
            f(*arg)

        finally:
            # filter and update regardless of success
            self.filter_and_update()
            self.field['state'] = _prev_state
            self.field.update()
            self.vbar.update()
            self.enable()

    def add_one_to_history(self, line: _RECORD) -> None:
        """
        add a record to the top of the text widget
        """
        self.change_contents(self.add_record, line)

    def remove_from_hour(self, record_id: int) -> None:
        """
        this is the callback that cleans a unit from the hour list
        """
        if record_id in self._hour_ids:
            self.change_contents(self._hour_ids.remove, record_id)

    def initialize_history(self, lines: _RECORDS) -> None:
        """
        check for new data
        perform init and then update display
        """
        self.change_contents(self._initialize_history, lines)

    def _on_show(self) -> None:
        """
        make entry Button kwargs with winfo_width
        """
        self.width = self.winfo_width()
        self.scrolled_width = self.width - self.vbar.winfo_width()
        self._kws |= dict(height=self._h, width=self.scrolled_width,
                          font=self.font)
        self.perform_controller_action(self, 'all')

    @staticmethod
    def double_click(evt: tk.EventType) -> None:
        """
        if double click lands on a button (history entry), invoke it
        """
        _button = evt.widget  # type: ignore
        invoke = getattr(_button, 'invoke', None)
        if invoke:
            with_enabled(_button)(invoke)()


class _HistorySelect(Cell):
    """
    acts as a button, toggling between dut history filter selections
    """
    _settings: Dict[str, str]
    initial_setting: str
    _history_attr: str
    _all_options: List[str]
    _next_index: int

    def __post_init__(self) -> None:
        self._label: Label = self._load(Label(self))
        self._all_options: List[str] = [self.initial_setting]
        self._next_index: int = 0
        self.current_option: str = self.initial_setting

    def _on_show(self) -> None:
        """
        set to initial state and disable
        index through settings including initial setting
        mark fresh setting visually
        """
        self.disable()

        _num_options = len(self._all_options)

        self.current_option = _option = self._all_options[self._next_index]
        self._next_index = (self._next_index + 1) % _num_options

        self._label.text(_option).color(self._settings.get(_option, APP.V.COLORS.text.normal))

        if _num_options > 1:
            self.fresh_data()

    def double_click(self, evt: tk.EventType):
        """
        button action
        set filter state var on History widget and update it
        """
        _ = evt
        self._on_show()
        _history = self.parent_widget(History)
        setattr(_history, self._history_attr, self.current_option)
        _history.filter_and_update()

    def set_options(self, options: List[str]) -> None:
        """
        set non-initial settings from the History widget after populating initial history
        """
        if not isinstance(options, list):
            options = [getattr(self.__class__, '_filtered_setting')] if options else []

        initial, *previous_options = self._all_options
        previous_options = list(previous_options)

        if options != previous_options:

            self._all_options = [initial] + options

            if self.current_option not in self._all_options:
                self._next_index = 0
                self._on_show()

            elif self.current_option == self.initial_setting:
                if not previous_options:
                    self._next_index = 1
                    self.fresh_data()


class HistoryPartNumber(_HistorySelect):
    initial_setting = 'all mns'
    _history_attr = '_model_setting'

    _settings = {
        initial_setting: APP.V.COLORS.metrics.label,
    }


class HistoryPassFail(_HistorySelect):
    initial_setting = 'p/f'
    _history_attr = '_pf_f'
    pass_string = 'p'
    fail_string = 'f'

    _settings = {
        initial_setting: APP.V.COLORS.metrics.label,
        pass_string: APP.V.COLORS.metrics.pass_text,
        fail_string: APP.V.COLORS.metrics.fail_text,
    }


class HistoryLength(_HistorySelect):
    initial_setting = 'd'
    _filtered_setting = 'h'
    _history_attr = '_len_f'

    _settings = {
        initial_setting: APP.V.COLORS.text.normal,
        _filtered_setting: APP.V.COLORS.text.normal,
    }


class HistoryRecency(_HistorySelect):
    initial_setting = 'all'
    _filtered_setting = 'last'
    _history_attr = '_recency_f'

    _settings = {
        initial_setting: APP.V.COLORS.text.normal,
        _filtered_setting: APP.V.COLORS.text.normal,
    }


WIDGET = Union[
    Mode,
    Metrics,
    History,
    HistoryPartNumber,
    HistoryPassFail,
    HistoryLength,
    HistoryRecency,
]

WIDGET_TYPE = Type[WIDGET]
