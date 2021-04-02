from dataclasses import dataclass
from typing import *

__all__ = [
    'SIZING',
    'Pos',
    'WidgetPosition',
    'Category',
]


class SIZING:
    SIZING = 0.25
    PAD_OFFSET = SIZING / 32
    L = 1 - SIZING
    S = SIZING
    M = L - S
    XS = S / 2
    XXS = XS / 3


@dataclass
class Pos:
    """
    represents a position (box) on the window
    (x, y, w, h)
    """
    x: float
    y: float
    w: float
    h: float

    @property
    def right(self) -> float:
        """
        relative float value of the right boundary of a position
        """
        return self.x + self.w

    @property
    def bottom(self) -> float:
        """
        relative float value of the bottom boundary of a position
        """
        return self.y + self.h

    @property
    def tuple(self) -> Tuple[float, ...]:
        """
        returns underlying relative values
        """
        return self.x, self.y, self.w, self.h


@dataclass
class WidgetPosition:
    """
    bundles a position with a widget
    """
    widget: Any
    pos: Union[Pos, Tuple[float, ...]]
    name: Optional[str] = None

    def __post_init__(self):
        self.pos = self.pos.tuple
        self.name = self.name or self.widget.__name__.lower()


@dataclass
class Category:
    """
    contains widget instances located at a position
    transformed at runtime
    """
    name: str
    widgets: Optional[Dict[int, Any]] = None
    showing: int = 0

    def __post_init__(self):
        self.index = 0
        self.showing = 0
        self.widgets = dict()

    def add(self, widget) -> None:
        """
        add a widget instance to category in window setup
        """
        self.widgets[self.index] = widget
        widget.category = self
        self.index += 1

    def cycle(self, forward: bool = True) -> Optional[bool]:
        """
        returns False if one widget in category to indicate that no action was taken
        else shows next widget in category
        """
        _mod = len(cast(dict, self.widgets))
        if _mod:
            self.showing = (self.showing + (1 if forward else -1)) % _mod
            self.widgets[self.showing].show()
        else:
            return False
