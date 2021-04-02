import itertools
import time

from base.concurrency import proxy
from src.instruments.base.daq import AIFinite
from src.instruments.base.daq import AIVoltageChannel
from src.instruments.base.daq import DAQChassis
from src.instruments.base.daq import DIChannel
from src.instruments.base.daq import DITask
from src.instruments.base.daq import DOChannel
from src.instruments.base.daq import DOTask

__all__ = [
    'PanelIDTask',
    'BoardPowerTask',
    'CurrentDrawTask',
]


class PanelIDTask(DITask):
    DEBOUNCE_LENGTH = 5

    chassis = DAQChassis(0x019F789B)
    module = chassis.module(1, 9401)
    CH0 = DIChannel(module, 0, 0)
    CH1 = DIChannel(module, 0, 1)
    CH2 = DIChannel(module, 0, 2)
    CH3 = DIChannel(module, 0, 3)
    CH4 = DIChannel(module, 0, 4)
    CH5 = DIChannel(module, 0, 5)
    CH6 = DIChannel(module, 0, 6)
    CH7 = DIChannel(module, 0, 7)

    @proxy.exposed
    def is_panel_present(self) -> bool:
        return bool(self.read_as_int())

    @proxy.exposed
    def test(self, duration: float) -> None:
        _timer = time.time
        tf = _timer() + duration
        while _timer() < tf:
            self.info('panel id:', self.read_as_int())

    def _instrument_debug(self) -> None:
        self.test(5.)


class BoardPowerTask(DOTask):
    chassis = DAQChassis(0x019F789B)
    module = chassis.module(2, 9474)
    CH0 = DOChannel(module, 0, 0)
    CH1 = DOChannel(module, 0, 1)
    CH2 = DOChannel(module, 0, 2)
    CH3 = DOChannel(module, 0, 3)
    CH4 = DOChannel(module, 0, 4)
    CH5 = DOChannel(module, 0, 5)
    CH6 = DOChannel(module, 0, 6)
    CH7 = DOChannel(module, 0, 7)

    @proxy.exposed
    def test(self, duration: float) -> None:
        _timer = time.time
        tf = _timer() + duration
        for ch in itertools.cycle(range(self.num_channels)):
            if not ch:
                self.all_off()
            self.set_one(ch, True)
            if _timer() >= tf:
                break

    def _instrument_debug(self) -> None:
        self.test(5.)


class CurrentDrawTask(AIFinite):
    acquisition_length_in_seconds = .001
    acquisition_rate_in_hertz = 1000

    chassis = DAQChassis(0x019F789B)
    module = chassis.module(0, 9221)
    CH0 = AIVoltageChannel(module, 0)
    CH1 = AIVoltageChannel(module, 1)
    CH2 = AIVoltageChannel(module, 2)
    CH3 = AIVoltageChannel(module, 3)
    CH4 = AIVoltageChannel(module, 4)
    CH5 = AIVoltageChannel(module, 5)
    CH6 = AIVoltageChannel(module, 6)
    CH7 = AIVoltageChannel(module, 7)

    def _process_data(self) -> None:
        pass

    @proxy.exposed
    def test(self, duration: float) -> None:
        _timer = time.time
        tf = _timer() + duration
        while _timer() < tf:
            self.info('current drawn:', self.read())

    def _instrument_debug(self) -> None:
        self.test(5.)
