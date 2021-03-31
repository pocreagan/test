from time import time
from typing import cast
from typing import Tuple

from src.base import register
from src.base.actor import proxy
from src.base.actor import configuration
from src.instruments.base.instrument import instrument_debug
from src.instruments.base.instrument import InstrumentError
from src.instruments.base.visa import VISA
from src.instruments.dc_power_supplies import DCLevel
from src.instruments.dc_power_supplies.base import _DCPowerSupply

__all__ = [
    'BKPowerSupply',
    'BKPowerSupplyError',
]


class BKPowerSupplyError(InstrumentError):
    pass


@instrument_debug
class BKPowerSupply(VISA, _DCPowerSupply):
    def calculate_knee(self, percent_of_max: float) -> DCLevel:
        raise NotImplementedError

    # ? W:\TestStation Data Backup\instruments\data\9200_Series_manual.pdf
    _config = configuration.from_yml(r'instruments\bk_power_supply.yml')
    display_name = _config.field(str)
    PATTERN = _config.field(str)
    MEASUREMENT_WAIT = _config.field(float)
    COMMAND_EXECUTION_TIMEOUT = _config.field(float)

    RAMP_STEPS: Tuple[DCLevel, ...] = (
        DCLevel(24., 15.),
        DCLevel(26., 13.8),
        DCLevel(28., 12.9),
        DCLevel(30., 12.),
        DCLevel(32., 11.3),
    )

    # noinspection SpellCheckingInspection
    class __Command:
        RESET = '*RST'
        SETUP = '*ESE 60;*SRE 48;*CLS'
        IS_DONE = '*OPC? '
        SET_VALUES = 'APPL %.6f,%.6f'
        GET_VALUES = 'APPL?'
        SET_OUTPUT = 'OUTP %d'
        GET_OUTPUT = 'OUTP?'
        GET_VOLT = ':MEAS:VOLT?'
        GET_CURR = ':MEAS:CURR?'
        GET_POW = ':MEAS:POW?'

    next_meas = 0.

    def _instrument_check(self) -> None:
        self.read(self.__Command.GET_VOLT)

    def __command(self, packet: str) -> None:
        self.write(packet)
        command_timeout = self.COMMAND_EXECUTION_TIMEOUT + time()
        while command_timeout > time():
            if self.read(self.__Command.IS_DONE):
                return
        raise BKPowerSupplyError(f'failed to confirm command {packet}')

    @proxy.exposed
    def send_reset(self):
        return self.__command(self.__Command.RESET)

    @register.after('_instrument_setup')
    def _bk_setup(self):
        self.__command(self.__Command.SETUP)
        self.next_meas = time()

    @register.after('_bk_setup')
    @register.before('_instrument_cleanup')
    def _bk_cleanup(self) -> None:
        self.write_settings(DCLevel(0., 0.), False)

    @proxy.exposed
    def read_settings(self) -> Tuple[DCLevel, bool]:
        return DCLevel(*self.read(self.__Command.GET_VALUES)), \
               bool(self.read(self.__Command.GET_OUTPUT))

    @proxy.exposed
    def set_settings(self, dc_level: DCLevel) -> None:
        self.__command(self.__Command.SET_VALUES % (dc_level.V, dc_level.A))

    @proxy.exposed
    def get_settings(self) -> DCLevel:
        return DCLevel(*self.read(self.__Command.GET_VALUES))

    @proxy.exposed
    def set_output(self, output_state: bool) -> None:
        self.__command(self.__Command.SET_OUTPUT % int(cast(bool, output_state)))

    @proxy.exposed
    def get_output(self) -> bool:
        return bool(self.read(self.__Command.GET_OUTPUT))

    @proxy.exposed
    def write_settings(self, dc_level: DCLevel = None, output_state: bool = None):
        if dc_level is None and output_state is None:
            raise BKPowerSupplyError('must call .write_settings() with at least one arg')

        was_dc_level_correct = (dc_level is None) or (dc_level == self.get_settings())
        if was_dc_level_correct:
            if dc_level is not None:
                self.info(f'power settings = {dc_level}')
        else:
            self.set_settings(dc_level)

        was_output_state_correct = (output_state is None) or not (output_state ^ self.get_output())
        if was_output_state_correct:
            if output_state is not None:
                self.info(f'output state = {output_state}')
        else:
            self.set_output(output_state)

        error_strings = []

        if not was_dc_level_correct:
            if self.get_settings() != dc_level:
                error_strings.append(dc_level)
            else:
                self.info(f'power settings = {dc_level}')

        if not was_output_state_correct:
            if self.get_output() ^ cast(bool, output_state):
                error_strings.append(f'output_enable={output_state}')
            else:
                self.info(f'output state = {output_state}')

        if error_strings:
            raise BKPowerSupplyError(f'failed to set to ' + ', '.join(error_strings))
        else:
            self.next_meas = time() + (self.MEASUREMENT_WAIT * 1.5)

    @proxy.exposed
    def measure(self, fresh: bool = True):
        """
        note that, even though we send the measure command, rather than the fetch command,
        the BK appears to be responding with a buffered value updated every 220ms
        this method returns in ~15ms unless @fresh, in which case it waits for the value to have been updated
        """
        if fresh:
            self._instrument_delay(self.next_meas - time())
            self.next_meas = time() + self.MEASUREMENT_WAIT
        return DCLevel(*list(map(self.read, [self.__Command.GET_VOLT, self.__Command.GET_CURR])))

    @proxy.exposed
    def ramp_up(self):
        self.write_settings(DCLevel(10, .5), True)
        for step in self.RAMP_STEPS:
            self.write_settings(step)

    @proxy.exposed
    def calculate_connection_state(self, calc):
        return _DCPowerSupply.calculate_connection_state(self, calc)

    @proxy.exposed
    def off(self):
        return _DCPowerSupply.off(self)

    def _instrument_debug(self) -> None:
        self.ramp_up()
        self.measure()
        self.write_settings(DCLevel(0., 0.))
        tf = time() + 5
        while time() < tf:
            self.info(self.measure())
