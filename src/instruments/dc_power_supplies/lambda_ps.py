from dataclasses import dataclass
from dataclasses import InitVar
from itertools import count
from typing import cast
from typing import Tuple
from typing import Union

from parse import parse

from src.base import register
from base.concurrency import proxy
from model import configuration
from src.instruments.base.bitfields import BitField
from src.instruments.base.bitfields import StatusBit
from src.instruments.base.instrument import instrument_debug
from src.instruments.base.instrument import InstrumentError
from src.instruments.base.serial import Serial
from src.instruments.dc_power_supplies import DCLevel
from src.instruments.dc_power_supplies.base import _DCPowerSupply

__all__ = [
    'LambdaPowerSupply',
    'LambdaPowerSupplyError',
]


class LambdaPowerSupplyError(InstrumentError):
    pass


@dataclass
class STTResponse:
    v_meas: float = None
    v_set: float = None
    i_meas: float = None
    i_set: float = None
    al: int = None
    os: int = None
    ps: int = None


class Command:
    def __init__(self, command_string: str, response_proto: str = None) -> None:
        self.command_string = command_string
        self.response_proto = response_proto

    def __set_name__(self, _, name: str) -> None:
        self.name = name
        self._repr_string = f'{type(self).__name__}({self.name}, {self.command_string})'

    def __get__(self, instance: 'LambdaPowerSupply', _) -> 'Command':
        self.instance = instance
        return self

    def __call__(self, argument: Union[int, float] = None):
        command = self.command_string
        if r'%' in self.command_string:
            if argument is None:
                raise LambdaPowerSupplyError(f'{self} requires an argument')
            command = command % argument

        for i in count():
            # noinspection PyBroadException
            try:
                self.instance.write(command)
                if self.response_proto is None:
                    return

                rx = self.instance.read()
                if not rx:
                    raise LambdaPowerSupplyError(f'{self} received no response')

                parsed = parse(self.response_proto, rx)
                if parsed is None:
                    raise LambdaPowerSupplyError(f'{self} failed to parse "{rx}"')

                return STTResponse(**parsed.named)  # type: ignore

            except LambdaPowerSupplyError:
                if i == self.instance.COMMAND_RETRIES:
                    raise

                continue

    def __repr__(self) -> str:
        return self._repr_string


@dataclass
class OperationStatusRegister(BitField.FromBinary):
    # noinspection PyDataclass
    value: InitVar[int]
    IS_ALARM_SET: bool = StatusBit()
    IS_OTP_SRQ_EN: bool = StatusBit()
    IS_OVP_SRQ_EN: bool = StatusBit()
    IS_FOLD_BACK_SRQ_EN: bool = StatusBit()
    IS_OUTPUT: bool = StatusBit()
    IS_AUTO_RESTART: bool = StatusBit()
    IS_FOLD_BACK_PRO_ENABLED: bool = StatusBit()
    IS_CC_MODE: bool = StatusBit()


@dataclass
class AlarmStatusRegister(BitField.FromBinary):
    # noinspection PyDataclass
    value: InitVar[int]
    PROGRAMMING_ERROR_OCCURRED: bool = StatusBit()
    FOLD_BACK_PRO_TRIPPED: bool = StatusBit()
    INPUT_AC_FAIL: bool = StatusBit()
    OTP_TRIPPED: bool = StatusBit()
    OVP_TRIPPED: bool = StatusBit()


@dataclass
class ErrorCodesRegister(BitField.FromBinary):
    # noinspection PyDataclass
    value: InitVar[int]
    WRONG_CURRENT: bool = StatusBit()
    WRONG_VOLTAGE: bool = StatusBit()
    BUFFER_OVERFLOW: bool = StatusBit()
    WRONG_COMMAND: bool = StatusBit()


@instrument_debug
class LambdaPowerSupply(Serial, _DCPowerSupply):
    def calculate_knee(self, percent_of_max: float) -> DCLevel:
        raise NotImplementedError

    _config = configuration.from_yml(r'config\lambda_power_supply.yml')
    display_name = _config.field(str)
    PORT = _config.field(str)
    BAUDRATE = _config.field(int)
    TIMEOUT = _config.field(float)
    TX_WAIT_S = _config.field(float)

    SET_SUCCESS_MARGIN = _config.field(float)
    COMMAND_RETRIES = _config.field(int)

    XON_X_OFF = False
    ENCODING = 'utf-8'
    TERM_CHAR = ''

    _set_address = Command(r'ADR01')
    _clear_error_registers = Command('DCL')
    _set_uvp_level = Command('UVP%04.1f')
    _set_ovp_level = Command('OVP%04.1f')
    _get_measurement = Command('STT?', 'AV{v_meas:f}SV{v_set:f}AA{i_meas:f}SA{i_set:f}OS{os}AL{al}PS{ps}')
    _set_output_state = Command('OUT%d')
    _set_voltage = Command('VOL%05.2f')
    _set_current = Command('CUR%06.3f')

    def __read_settings(self) -> Tuple[DCLevel, DCLevel]:
        """
        returns settings obj, measurement obj
        """
        results = cast(STTResponse, self._get_measurement())
        self.alarms = AlarmStatusRegister(results.al)
        self.operations_status = OperationStatusRegister(results.os)
        self.error_codes = ErrorCodesRegister(results.ps)
        return DCLevel(results.v_meas, results.i_meas), DCLevel(results.v_set, results.i_set)

    @proxy.exposed
    def measure(self, fresh: bool = True) -> DCLevel:
        _ = fresh
        return self.__read_settings()[0]

    @proxy.exposed
    def set_settings(self, dc_level: DCLevel) -> None:
        self._set_voltage(dc_level.V)
        self._set_current(dc_level.A)

    @proxy.exposed
    def set_output(self, output_state: bool) -> None:
        self._set_output_state(output_state)

    def get_settings(self) -> DCLevel:
        raise NotImplementedError

    def get_output(self) -> bool:
        raise NotImplementedError

    @proxy.exposed
    def write_settings(self, dc_level: DCLevel = None, output_state: bool = None):
        if dc_level is None and output_state is None:
            raise LambdaPowerSupplyError('must call .write_settings() with at least one arg')

        if dc_level is not None:
            self.set_settings(dc_level)

        if output_state is not None:
            self.set_output(output_state)

        error_strings = []
        _, settings = self.__read_settings()

        if dc_level is not None:
            _margin = self.SET_SUCCESS_MARGIN
            for read, exp in ((settings.V, dc_level.V), (settings.A, dc_level.A)):
                if not ((exp - _margin) < read < (exp + _margin)):
                    error_strings.append(dc_level)
                    break
            else:
                self.debug(f'power settings = {settings}')

        if output_state is not None:
            if self.operations_status.IS_OUTPUT ^ output_state:
                error_strings.append(f'output_enable={output_state}')
            else:
                self.debug(f'output state = {output_state}')

        if error_strings:
            raise LambdaPowerSupplyError(f'failed to set to ' + ', '.join(error_strings))

    @register.after('_instrument_setup')
    def _lambda_setup(self) -> None:
        self._set_address()
        self._set_uvp_level(0.)
        self._set_ovp_level(60.)
        self._lambda_cleanup()
        if self.alarms or self.error_codes:
            self._clear_error_registers()

    @register.before('_instrument_cleanup')
    def _lambda_cleanup(self) -> None:
        self.write_settings(DCLevel(0., 0.), False)

    def _instrument_check(self) -> None:
        self._get_measurement()

    @proxy.exposed
    def test(self):
        for _ in range(10):
            self.write_settings(DCLevel(12, 0.1), True)
            self.write_settings(DCLevel(14, 0.2))
            self.write_settings(DCLevel(16, 0.3))
            self.write_settings(DCLevel(10, 0.4))
            self.write_settings(output_state=False)

    def _instrument_debug(self) -> None:
        self.test()
