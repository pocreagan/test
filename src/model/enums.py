from enum import auto
from typing import Type

from src.base.general import EqEnum

__all__ = [
    'Station',
    'LeakTestStage',
    'EEPROMTarget',
    'TestResult',
    'MouseAction',
]


class TestResult(EqEnum):
    PASS = auto()
    FAIL = auto()


class MouseAction(EqEnum):
    LEFT = 0
    RIGHT = auto()
    TOP = auto()
    BOTTOM = auto()
    CLICK = auto()

    @property
    def is_directional(self) -> bool:
        return self != MouseAction.CLICK

    @property
    def type(self) -> str:
        return 'drag' if self.is_directional else 'click'

    def _check_is_directional(self) -> None:
        if not self.is_directional:
            raise ValueError('MouseAction.CLICK has no axis or direction')

    @property
    def axis(self) -> str:
        self._check_is_directional()
        return 'vertical' if self.value // 2 else 'horizontal'

    @property
    def direction(self) -> bool:
        self._check_is_directional()
        return bool(self.value % 2)

    def __call__(self, x: int, y: int) -> 'MouseAction':
        """
        add click coordinates and return self instance
        """
        self.click_coordinates = x, y
        return self

    def __setstate__(self, state):
        super().__set_state__(state)
        co = getattr(state, 'click_coordinates', None)
        if co is not None:
            self(*co)

    def __getstate__(self):
        state = super().__getstate__()
        state.click_coordinates = getattr(self, 'click_coordinates', None)
        return state

class Station(EqEnum):
    MASTER = auto()
    LL1 = auto()
    LL2 = auto()
    LL3 = auto()
    PSU1 = auto()
    PSU2 = auto()
    BRIGHT = auto()


class LeakTestStage(EqEnum):
    F_FILL = auto()
    FILL = auto()
    SETTLE = auto()
    TEST = auto()
    VENT = auto()
    PASS = auto()
    LEAK = auto()
    LO_PRESSURE = auto()
    HI_PRESSURE = auto()
    GROSS_LEAK = auto()
    ERROR = auto()

    @classmethod
    def get(cls, k: str) -> Type['LeakTestStage']:
        return cls[k.replace(' ', '_').upper()]


class EEPROMTarget(EqEnum):
    CONFIG = 5
    LEGACY = 7
    COMPENSATION = 8
