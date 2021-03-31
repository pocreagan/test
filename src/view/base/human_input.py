import math
import re
import tkinter as tk
from functools import partial
from typing import *

from framework.base import message
from framework.base.general import call
from framework.base.general import do_if_not_done
from framework.base.log import logger
from framework.model import APP
from framework.model.enums import MouseAction

__all__ = [
    'HID',
]


log = logger(__name__)


class Binding:
    parent_methods: set[str] = None

    def check_parent(self):
        """
        ensure on init that all parent methods needed for HID are defined on Window
        """
        assert self.parent_methods is not None
        assert all(hasattr(self.parent, k) for k in self.parent_methods)

    def __init__(self, parent: tk.Tk) -> None:
        """
        get bindings from ini, clear state, and perform initial event binding
        """
        self.name = self.__class__.__name__
        self.parent = parent
        self.check_parent()
        self.constants = APP.V.hid.get(self.name.lower())
        self.bindings: dict[str, dict[str, str]] = self.constants['bindings']
        self.__post_init__()
        self._active = True
        self.bind()

    @do_if_not_done('bound', True)
    def bind(self) -> None:
        """
        register events for application-side methods in the Tk system
        """
        for k, v in self.bindings.items():
            for f_name, binding in v.items():
                self.parent.bind(binding, getattr(self, k))
                log.debug(f'{binding} --> {self.name}.{f_name}()')
        self.clear()
        log.info(f'bound {self.name} events')

    @do_if_not_done('bound', False)
    def unbind(self) -> None:
        """
        stop capturing HID events in the Tk system
        """
        for k, v in self.bindings.items():
            for f_name, binding in v.items():
                self.parent.unbind(binding)
                log.debug(f'{binding} -/> {self.name}.{f_name}()')
        log.info(f'unbound {self.name} events')

    @do_if_not_done('active', False)
    def mute(self) -> None:
        """
        prevent captured events from having any effect outside of the TK binding system
        """
        self.clear()

    @do_if_not_done('active', True)
    def unmute(self) -> None:
        """
        undo mute()
        """

    def clear(self) -> None:
        """
        reset event handling state
        """
        raise NotImplementedError

    def __post_init__(self) -> None:
        """
        perform actions after init and before initial Tk event binding
        """


class Keyboard(Binding):
    """
    encapsulates keyboard event handling for the Window
    """
    scan_string: str = None
    parent_methods = {
        'clipboard_get',
        'clipboard_clear',
        'clipboard_append',
        'handle_keyboard_action',
    }

    def __post_init__(self) -> None:
        """
        set ini values as attributes and add scan parsers
        """
        regex = self.constants['re']
        self._keypress_re = re.compile(regex['KEYPRESS'])
        self._start_char: str = regex['START_CHAR']
        self._end_char: str = regex['END_CHAR']

        special_k_re = re.compile(r'(\w)>$')
        special_character_d = self.bindings['special_character']
        self.special_keys = {special_k_re.findall(v)[0]: k for k, v in special_character_d.items()}

        self.parse_funcs: list[tuple[re.Pattern, str]] = []
        for k in APP.STATION.scan_parsers:
            # compile ini regex and map to method name, ex: ..., 'dut_scan'
            f, _re = f'{k.lower()}_scan', APP.V.hid['keyboard']['re'][k]
            self.parse_funcs.append((re.compile(_re), f))
            log.debug(f'added parser "{_re}" -> {f}')

    def clear(self) -> None:
        """
        reset state
        """
        self.scan_string = ''

    def handle(self, f: str, *args) -> None:
        """
        if method mapped to keyboard action is defined in Keyboard, perform it
        else pass up to Window for handling
        """
        self.clear()
        if method := getattr(self, f, None):
            method(*args)
        else:
            self.parent.handle_keyboard_action(message.KeyboardAction(f, *args))

    def parse(self, s: str) -> None:
        """
        try each parser defined by station and handle first match
        """
        for pattern, f in self.parse_funcs:
            if parsed := pattern.findall(s):
                return self.handle(f, *parsed[0])

    # bound methods
    def special_character(self, evt: tk.EventType) -> None:
        """
        gates handling for mapped special char method with _active
        """
        if self._active and evt.keysym:
            self.handle(self.special_keys[evt.keysym])

    def capture(self, evt: tk.EventType) -> None:
        """
        handles each standard character typed or scanned into window
        """
        if self._active and evt.char:
            c = evt.char
            if c == self._start_char:
                self.scan_string = self._start_char
            elif self._keypress_re.search(c):
                self.scan_string += c
                if c == self._end_char:
                    self.parse(self.scan_string)

    # hid-level special character handlers
    def paste(self) -> None:
        """
        grabs clipboard and handles contents as if they were typed into the window
        """
        self.parse(self.parent.clipboard_get())

    def copy(self) -> None:
        """
        writes application build information to clipboard
        """
        self.parent.clipboard_clear()
        self.parent.clipboard_append(APP.FREEZE)


class Mouse(Binding):
    """
    encapsulates mouse event handling for the Window
    """
    _release_methods = ['click', 'drag_h', 'drag_v']
    press_event: Optional[tk.EventType] = None
    co_dimensions: Optional[tuple[tuple[int, ...], ...]] = None
    parent_methods = {
        'update',
        'winfo_rootx',
        'winfo_rooty',
    }

    # calculate drag angle categories and drag length threshold from view ini
    __responsiveness = APP.V.hid['mouse']['responsiveness']
    _drag = int(__responsiveness['CLICK_SWIPE_THRESHOLD_PX'])

    # square click threshold once, here, to speed up mouse action filter
    _drag_sq = _drag ** 2
    __fudge = __responsiveness['DISTANCE_FROM_RIGHT_ANGLE_DEGREES_ALLOWED']

    _directions: dict[int, MouseAction] = dict()
    for deg in range(-180, 181):
        for _min, _max, direction in ((-__fudge, __fudge, MouseAction.RIGHT),
                                      (-180, -(180 - __fudge), MouseAction.LEFT),
                                      ((180 - __fudge), 180, MouseAction.LEFT),
                                      (-90 - __fudge, -90 + __fudge, MouseAction.TOP),
                                      (90 - __fudge, 90 + __fudge, MouseAction.BOTTOM),):
            if _min <= deg < _max:
                _directions[deg] = direction

    def clear(self) -> None:
        """
        reset initial press state
        """
        self.press_event, self.co_dimensions = None, None

    def validate(self, evt: tk.EventType):
        """
        if mouse action is within the bounds of a widget, rather than in the padding,
        return the widget
        """
        if self._active and evt.widget:
            if (cell := evt.widget.master) is not None:
                if getattr(cell, 'is_enabled', False):
                    return cell

    # initial event handlers
    def press(self, evt: tk.EventType) -> str:
        """
        handles every press event, including the first and second in a double click
        """
        if _cell := self.validate(evt):
            # persist the event for other handlers
            self.press_event = evt

            # set widget root bounds from current window dimensions
            self.parent.update()
            x, y = self.parent.winfo_rootx(), self.parent.winfo_rooty()
            (x0, x1), (y0, y1) = _cell.co_dimensions_raw
            self.co_dimensions = (x + x0, x + x1), (y + y0, y + y1)

        # stop event handling chain
        return 'break'

    def double_click(self, evt: tk.EventType) -> None:
        """
        pass double click event to cell if handler is defined
        disregards initial press state
        """
        if cell := self.validate(evt):
            call(cell, 'double_click', evt)
        self.clear()

    # gates: secondary handler if True
    @property
    def initial_target(self):
        """
        secondary events should only proceed if initial state has been set
        returns target cell widget
        """
        if _cell := self.press_event:
            if self._active:
                return _cell.widget.master
            self.clear()

    def is_in_bounds(self, x_root: int, y_root: int) -> bool:
        """
        determine if non-first event in sequence is still within first event's widget
        """
        try:
            (x_min, x_max), (y_min, y_max) = self.co_dimensions
        except TypeError:
            return False
        else:
            return (x_min < x_root < x_max) and (y_min < y_root < y_max)

    # secondary event handlers
    def release(self, evt: tk.EventType) -> None:
        """
        perform all calculations only on mouse release
        handle if all conditions are met by press - release pair
        clear state regardless
        """
        if cell := self.initial_target:

            click, drag_h, drag_v = [getattr(cell, k, None) for k in self._release_methods]

            if click or drag_h or drag_v:

                # unpack release coordinates
                x, y = evt.x_root, evt.y_root

                if self.is_in_bounds(x, y):
                    # if release is in pressed widget's bounds, calculate distances traveled in x and y
                    dx, dy, _th = x - self.press_event.x_root, y - self.press_event.y_root, self._drag

                    if (dx > _th) or (dy > _th) or ((dx ** 2 + dy ** 2) > self._drag_sq):
                        if drag_h or drag_v:

                            # if mouse traveled far enough, determines drag angle
                            if _d := self._directions.get(int(math.degrees(math.atan2(dy, dx))), None):
                                # if drag angle sufficiently vertical or horizontal, handles drag
                                # by direction in cell
                                _dir = _d.direction

                                if drag_h and _dir == 'horizontal':
                                    drag_h(_d)

                                elif drag_v and _dir == 'vertical':
                                    drag_v(_d)

                    elif click:
                        # handle as click in cell if it hasn't dragged past threshold
                        click()

        call(cell, 'on_release')
        self.clear()


class HID:
    """
    aggregates Keyboard and Mouse instances for combined actions in Window
    to debounce hid events, perform actions in a with <HID instance>: context manager
    """

    def _do_all(self, f: str) -> None:
        """
        call the same method on all children
        """
        [getattr(child, f)() for child in self.children]

    def __init__(self, parent: tk.Tk) -> None:
        self.mouse = Mouse(parent)
        self.keyboard = Keyboard(parent)
        self.children = [self.mouse, self.keyboard]
        map_to_children = Callable[[], None]
        self.bind: map_to_children = partial(self._do_all, f='bind')
        self.unbind: map_to_children = partial(self._do_all, f='unbind')
        self.mute: map_to_children = partial(self._do_all, f='mute')
        self.unmute: map_to_children = partial(self._do_all, f='unmute')

    def __enter__(self):
        """
        stop paying attention to hid events while encapsulated code executes
        """
        self.mute()

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        when the context manager completes execution, start handling hid events again
        """
        self.unmute()

