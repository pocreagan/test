import tkinter as tk
from functools import wraps
from tkinter import ttk
from typing import Callable
from typing import Optional
from typing import Union

from src.base.general import chain
from src.base.log import logger
from src.model.resources import COLORS

__all__ = [
    'Label',
    'Message',
    'Scrollbar',
    'ProgressBar',
    'StepProgress',
    'Canvas',
]

log = logger(__name__)


class Label:
    _obj_type = tk.Label

    def __init__(self, parent, anchor: str = 'center', justify: str = 'center',
                 fg: str = COLORS.white, bg: str = COLORS.medium_grey,
                 font=None, **kwargs) -> None:
        self.parent = parent
        self.parent.labels.append(self)
        self.var = tk.StringVar()
        _kw = dict(anchor=anchor, justify=justify, textvariable=self.var,
                   fg=fg, bg=bg, font=font or parent.font)
        self.parent_normal_bg = _kw['bg']
        self.object = self._obj_type(parent, **_kw, **kwargs)
        self.is_packed, self.is_placed, self.is_grid = False, False, False
        self._last_text = ''
        self._current_config = dict()

    @property
    def is_showing(self) -> bool:
        """
        returns has been placed or packed in parent
        """
        return self.is_placed or self.is_packed or self.is_grid

    @chain
    def text(self, text: str):
        """
        writes to the StringVar instance
        """
        if text != self._last_text:
            self.var.set(text)

        self._last_text = text

    @chain
    def config(self, **kwargs):
        """
        passes kwargs through to tk.Label object
        """
        for k, v in kwargs.items():
            if k not in self._current_config:
                break

            if self._current_config[k] != v:
                break

        else:
            return

        self.object.config(**kwargs)
        self._current_config.update(kwargs)

    @wraps(config)
    def cfg(self, **kwargs):
        return self.config(**kwargs)

    @chain
    def color(self, fg: str = None, bg: str = None):
        """"
        specific subset of config()
        """
        self.config(**{k: v for k, v in zip(('fg', 'bg'), (fg, bg)) if v is not None})

    @chain
    def place(self, x: float, y: float, height: float, width: float):
        """
        show widget with x, y, w, h relative to parent
        """
        if not self.is_showing:
            self.object.place(relx=x, rely=y, relheight=height, relwidth=width)
            self.is_placed = True

    @chain
    def pack(self, *args, **kwargs):
        """
        expose widget pack method
        """
        if not self.is_showing:
            if (not args) and (not kwargs):
                self.object.pack(fill=tk.BOTH, expand=1)

            else:
                self.object.pack(*args, **kwargs)

            self.is_packed = True

    @chain
    def grid(self, row: int, column: int):
        """
        expose widget pack method
        """
        if not self.is_showing:
            self.object.grid(row=row, column=column)

            self.is_packed = True

    @chain
    def forget(self):
        """
        calls appropriate method to remove widget from view
        """
        if self.is_showing:
            if self.is_packed:
                self.object.pack_forget()

            elif self.is_placed:
                self.object.place_forget()

            elif self.is_grid:
                self.object.grid_forget()

        self.is_packed, self.is_placed, self.is_grid = False, False, False


class Message(Label):
    """
    multiline variant of Label, above
    """
    _obj_type = tk.Message


class Scrollbar(ttk.Scrollbar):
    """
    override with custom style using ttk
    """
    # ? https://stackoverflow.com/a/29583609
    style_made: bool = False

    def __init__(self, parent):
        if not self.__class__.style_made:
            style = ttk.Style()
            style.theme_use('clam')
            dark_c = COLORS.black
            medium_c = COLORS.medium_grey
            light_c = COLORS.white
            style.configure("Vertical.TScrollbar", gripcount=0,
                            background=dark_c,
                            darkcolor=medium_c,
                            lightcolor=medium_c,
                            troughcolor=dark_c,
                            bordercolor=dark_c,
                            arrowcolor=light_c,
                            )
            self.__class__.style_made = True
        self.objects = list()
        super().__init__(parent, orient="vertical", command=self.on_scroll)

    def on_scroll(self, *args) -> None:
        [o.yview(*args) for o in self.objects]

    def on_mouse_wheel(self, evt: tk.EventType) -> str:
        [o.yview('scroll', -evt.delta, 'units') for o in self.objects]
        return 'break'

    def bind_to(self, o) -> None:
        """
        set self.command for the scrollbar
        """
        self.objects.append(o)
        o.configure(yscrollcommand=self.set)
        o.bind("<MouseWheel>", self.on_mouse_wheel)


class ProgressBar(ttk.Progressbar):
    """
    override with custom style using ttk
    """
    # ? https://stackoverflow.com/a/56678946
    # ? https://docs.python.org/3/library/tkinter.ttk.html#progressbar

    style_made: bool = False

    def __init__(self, parent, width: int) -> None:
        if not self.__class__.style_made:
            style = ttk.Style()
            style.theme_use('clam')
            dark_c = COLORS.black
            light_c = COLORS.white
            style.configure("Horizontal.TProgressbar",
                            troughcolor=dark_c,
                            bordercolor=dark_c,
                            background=light_c,
                            lightcolor=dark_c,
                            darkcolor=dark_c)
            self.__class__.style_made = True

        self.last_value = 0.
        self.value = tk.DoubleVar()
        super().__init__(parent, variable=self.value, orient="horizontal",
                         mode='determinate', maximum=1., length=width)

    @property
    def is_complete(self) -> bool:
        return self['maximum'] == self.last_value

    def setup(self, value: float) -> None:
        assert value != 0.
        self['maximum'] = value
        self.set(0.)

    def increment(self) -> None:
        self.last_value += 1
        self.value.set(self.last_value)

    def set(self, val: float) -> None:
        self.last_value = min(val, self['maximum'])
        self.value.set(self.last_value)
        self.update()


class Canvas(tk.Canvas):
    # ? https://stackoverflow.com/a/9576938
    def __init__(self, parent, **kwargs) -> None:
        self._layers = set()
        if not kwargs:
            kwargs = dict(width=parent.w_co, height=parent.h_co)
        super().__init__(parent, **kwargs)

    def add(self, layer: int, command: Callable, *args, **kwargs) -> str:
        layer_tag = "layer %s" % layer
        self._layers.add(layer_tag)

        tags = kwargs.setdefault("tags", [])
        tags.append(layer_tag)

        _item = command(*args, **kwargs)
        [self.lift(layer) for layer in sorted(self._layers)]
        return _item


STEP_SIZE_PX = 100


class StepProgress(tk.Frame):
    def __init__(self, parent, text: str, h: int, **kwargs) -> None:
        self.parent = parent

        self.labels = list()
        self.font = self.parent.font

        super().__init__(parent, bg=COLORS.black, height=h, **kwargs)

        self.label = Label(self, bg=COLORS.dark_grey)
        self._original_text = text
        self.label.text(self._original_text)
        self.label.pack(fill=tk.BOTH, expand=1)

        self.progress_bar: ProgressBar = ProgressBar(self, self.parent.w_co)

    def start_progress(self, minor_text: Optional[str], max_val: Optional[Union[int, float]]) -> None:
        self.minor_text(minor_text)
        self.label.color(COLORS.white, COLORS.black)

        if max_val is not None:
            if not self.progress_bar.winfo_ismapped():
                self.progress_bar.setup(max_val)
                self.progress_bar.pack(fill=tk.X, expand=1)

    def set_progress(self, value: float) -> None:
        self.progress_bar.set(value)

    def minor_text(self, minor_text: Optional[str]) -> None:
        if minor_text:
            return self.label.text(f'{self._original_text} - {minor_text}')
        self.label.text(self._original_text)

    def end_progress(self, success: Optional[bool]) -> None:
        if self.progress_bar.winfo_ismapped():
            self.progress_bar.pack_forget()

        if success is None:
            color = COLORS.white
        else:
            color = COLORS.green if success else COLORS.red
            if success:
                self.minor_text(None)
        self.label.color(color, COLORS.dark_grey)
