from src.base.log import logger
from src.view.base.placement import SIZING
from src.view.base.window import *
from src.view.widgets.dynamic import *
from src.view.widgets.history import *
from src.view.widgets.static import *

__all__ = [
    'Window',
]

log = logger(__name__)


class Window(Window):
    _station: int = 1
    widgets = [
                  (Logo, (0, 0, SIZING.S, SIZING.S)),
                  (Stats, (0, SIZING.S, SIZING.S, SIZING.L - SIZING.XXS)),
                  (Instruments, (0, 1 - SIZING.XXS, SIZING.S, SIZING.XXS)),
              ] + [
                  (Metrics, (i * SIZING.S, 0, SIZING.S, SIZING.S), f'metrics_{i}') for i in range(1, 4)
              ] + [
                  (Chart, (SIZING.S, SIZING.S, SIZING.L, SIZING.L)),
                  (Logging, (SIZING.S, SIZING.S, SIZING.L, SIZING.L)),
              ]

    def _swap_station_to(self, new_station: int) -> None:
        self._station = new_station
        [getattr(self, f'metrics_{i}').disable() for i in range(1, self.stations_max + 1)]
        getattr(self, f'metrics_{self._station}').enable()
        log.info(f'swapped station to {self._station}')

    def swap_station(self, is_right: bool = False, direct: int = None) -> None:
        if direct is None:
            new_station = self._station + (1 if is_right else -1)
            if new_station < 1 or new_station > self.stations_max:
                return
            self._swap_station_to(new_station)
        else:
            self._swap_station_to(direct)

    def __post_init__(self) -> None:
        self.swap_station(direct=self.stations_max)
