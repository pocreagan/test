import tkinter as tk
from pathlib import Path
from tkinter.font import Font
from typing import *

import PIL
from PIL import ImageTk

from src.base.concurrency.concurrency import ChildTerminus
from src.base.general import do_if_not_done
from src.base.load import tuple_to_hex_color
from src.base.log import logger
from src.view.base import component
from src.view.base.window import Window
from src.view.base.placement import Category

__all__ = [
    'Cell',
    'Static',
]

log = logger(__name__)


class Cell(ChildTerminus, tk.Frame):
    """
    wrapper around tk.Frame
    define _click(action) | _drag(action) to respond to mouse events in a widget
    """
    __font: tk.font.Font = None
    parent: Window
    is_enabled: bool = True
    content: tk.Label = None
    _enable_state_vars = {True: (APP.V.COLORS.background.lighter, 'enabled'),
                          False: (APP.V.COLORS.background.normal, 'disabled'), }
    _fresh_interval_ms: int = APP.V.window['fresh_data_interval_ms']
    _fresh_sequence: List[str] = [
        tuple_to_hex_color((v, v, v)) for v in range(APP.V.grey['light'], APP.V.grey['medium'], -1)
    ]
    category: Category

    @property
    def font(self) -> tk.font.Font:
        if not self.__font:
            f = getattr(APP.V.FONTSIZE, self.__class__.__name__.upper(), None)
            if f:
                self.__font = self._make_font(f)
            else:
                self.__font = self.parent.font.tk_font
        return self.__font

    @font.setter
    def font(self, font: tk.font.Font) -> None:
        self.__font = font

    # SUPPRESS-LINTER <super().__init__ called immediately after first call of show()>
    # noinspection PyMissingConstructor
    def __init__(self, name: str, parent: Window, x: float, y: float, w: float, h: float, ) -> None:
        """
        calc relative dimensions using padding from ini
        calc actual frame dimensions in pixels for hid.Mouse
        make widget default font
        """
        self.parent = parent
        self.perform_controller_action = self._perform_other_action

        self.name = name
        self.pos = x, y, w, h
        self._made = False
        self.labels = list()
        self.scheduled_reference = None
        self._normal_bg = None
        self.constants = APP.V.widget_constants.get(self.__class__.__name__, dict())
        self._fresh_index = None

    def __post_init__(self):
        """
        perform subclass-specific setup here
        set to initial state, request controller update if necessary
        """
        raise NotImplementedError

    @do_if_not_done('made', True)
    def _cell_make(self) -> None:
        """
        compute dimensions and call overridden make()
        """
        tk.Frame.__init__(self, self.parent)
        self.config(bg=APP.V.COLORS.background.normal)

        # compute relative dimensions
        x, y, w, h = self.pos
        _y_pad = APP.V.window['PADDING']
        _x_pad = _y_pad / self.parent.screen.w_h_ratio
        _y_shift, _x_shift = _y_pad if y == 0 else 0, _x_pad if x == 0 else 0
        _rel_x = x + _x_shift
        _rel_y = y + _y_shift
        _rel_width = (w - _x_pad) - _x_shift
        _rel_height = (h - _y_pad) - _y_shift

        # dimensions relative where (1,1) is the bottom right of the Window
        self._place_dimensions = dict(relx=_rel_x, rely=_rel_y, relwidth=_rel_width, relheight=_rel_height)

        # compute absolute dimensions
        self.x_co = int(_rel_x * self.parent.w_px)
        self.y_co = int(_rel_y * self.parent.h_px)
        self.w_co = int(_rel_width * self.parent.w_px)
        self.h_co = int(_rel_height * self.parent.h_px)

        # dimensions of this widget in pixels
        self.co_dimensions_raw = (self.x_co, self.x_co + self.w_co), (self.y_co, self.y_co + self.h_co)

        self.__post_init__()

    def _remove_previous(self):
        """
        if a Cell exists in the same position, removes it
        """
        previous_widget = self.parent.widgets_by_position.get(self.pos, None)
        if previous_widget:
            previous_widget.hide()

    def _before_show(self) -> None:
        """
        called before the last widget is removed
        """

    def _on_show(self):
        """
        called just after place()
        start update scheduler etc
        """

    @do_if_not_done('showed', True)
    def show(self):
        """
        place frame on Window using relative values calculated in __init__
        if a widget already exists in this position, hides it first
        """
        self._cell_make()
        self._before_show()
        self._remove_previous()
        self.parent.widgets_by_position[self.pos] = self
        self.place(**self._place_dimensions)
        self.update()
        self._on_show()

    def _on_hide(self):
        """
        executes just before hide()
        """

    @do_if_not_done('showed', False)
    def hide(self):
        """
        remove frame from Window
        """
        self.cancel_scheduled()
        self._on_hide()
        self.place_forget()

    def _before_destroy(self):
        """
        executes just before Tk.Frame.destroy()
        """

    def destroy(self):
        """
        overridden as a template hook
        """
        try:
            self.cancel_scheduled()
            self._before_destroy()
        except Exception as e:
            print(self.name, e, 'in close')
        super().destroy()

    # # # appearance methods
    def _set_background(self, color: str) -> None:
        """
        set the background color of self and label children
        """
        _last_color = getattr(self, '__last_color', None)
        if _last_color is None or _last_color != color:
            self.config(bg=color)
            [label.color(bg=color) for label in self.labels]
            setattr(self, '__last_color', color)

    def _toggle_enabled(self, is_enabled: bool) -> None:
        """
        change frame background to color from ini
        """
        color, s = self._enable_state_vars[is_enabled]
        self.parent.after_idle(self._set_background, color)
        log.debug(f'window widget <{self.name}> {s}')
        self.is_enabled = is_enabled

    def enable(self, *args, **kwargs) -> None:
        """
        expose partial _toggle_enabled to callers
        """
        _, _ = args, kwargs
        self._toggle_enabled(True)

    def disable(self, *args, **kwargs) -> None:
        """
        expose partial _toggle_enabled to callers
        """
        _, _ = args, kwargs
        self._toggle_enabled(False)

    def _make_more_stale(self) -> None:
        """
        darken from light to enabled on interval, then enable
        """
        self._fresh_index += 1
        try:
            self.parent.after_idle(self._set_background, self._fresh_sequence[self._fresh_index])
            # self._set_background(self._fresh_sequence[self._fresh_index])
            self.schedule(self._fresh_interval_ms, self._make_more_stale)
        except IndexError:
            self.schedule(self._fresh_interval_ms, self.enable)

    def fresh_data(self):
        """
        indicate fresh data with temporary background highlight
        debounce fresh data re-fetch per ini
        """
        self._fresh_index = -1
        self._make_more_stale()

    # # # schedule methods
    def schedule(self, interval: int, callback: Callable, *args):
        """
        calls after() and registers reference for future cancelling
        """
        self.scheduled_reference = self.parent.after(interval, callback, *args)

    def cancel_scheduled(self):
        """
        cancels scheduled callback if any
        """
        if self.scheduled_reference:
            try:
                self.parent.after_cancel(self.scheduled_reference)
            except Exception as e:
                log.error(str(e))

    # # # load methods
    def _load(self, tk_widget, name='content', **kwargs):
        """
        remove existing content and
        pack new child widget to fill entire frame
        return child widget
        """
        existing = getattr(self, name, None)
        if existing:
            for method in ['forget', 'pack_forget', 'destroy']:
                # SUPPRESS-LINTER <don't care if this fails>
                # noinspection PyBroadException
                try:
                    getattr(existing, method)()
                except Exception as _:
                    pass

        setattr(self, name, tk_widget)

        if kwargs:
            getattr(self, name).place(**kwargs)

        else:
            getattr(self, name).pack(fill=tk.BOTH, expand=1)

        return getattr(self, name)

    def _make_font(self, size: int, family: str = None) -> Font:
        """
        make new Tk font instance for widget, font name can be overridden if different from parent's
        """
        return Font(family=family or self.parent.font.name, size=size)

    @staticmethod
    def _make_image(fp: Union[Path, str], dimensions_in_pixels: Tuple[int, ...] = None) -> ImageTk.PhotoImage:
        """
        take filepath from ini
        resize if necessary
        return TK-compatible object to be packed in frame
        """
        img = PIL.Image.open(str(fp))
        if dimensions_in_pixels:
            img = img.resize(dimensions_in_pixels)

        return ImageTk.PhotoImage(img)


class Static:
    class String(Cell):
        """
        show human readable test station title
        """
        label: component.Label
        string: str

        def __post_init__(self):
            self.label = self._load(component.Label(self, anchor="center", font=self.font, ))
            self.label.text(self.string)
            self.disable()

    class Image(Cell):
        """
        show human readable test station title
        """
        filepath: str
        img: tk.PhotoImage
        _force_enabled: bool = False

        def __post_init__(self):
            if not self._force_enabled:
                self.disable()
            else:
                self.enable()
            self.config(bg=APP.V.COLORS.background.normal)
            self.img = self._make_image(APP.R.img(self.filepath))
            self._load(tk.Label(self, anchor='center', image=self.img,
                                bg=APP.V.COLORS.background.darker))
