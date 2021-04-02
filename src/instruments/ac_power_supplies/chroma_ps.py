import csv
from dataclasses import dataclass
from dataclasses import fields
from dataclasses import InitVar
from dataclasses import MISSING
from enum import auto
from enum import Enum
from operator import attrgetter
from operator import is_
from typing import cast
from typing import Dict
from typing import Optional
from typing import Type
from typing import TypeVar
from typing import Union

from src.base import register
from base.concurrency import proxy
from model import configuration
from src.instruments.base.bitfields import BitField
from src.instruments.base.bitfields import StatusBit
from src.instruments.base.instrument import instrument_debug
from src.instruments.base.instrument import InstrumentError
from src.instruments.base.serial import Serial

__all__ = [
    'ChromaPowerSupply',
]

ARG_T = Union[str, int, float]


class _Branch(Enum):
    SOURCE = 0
    MEASURE = auto()
    OUTPUT = auto()
    STATUS = auto()


_T = TypeVar('_T')


class ChromaPowerSupplyError(InstrumentError):
    pass


class MeasurementMessage:
    # noinspection PyTypeChecker
    _T = TypeVar('_T', bound='MeasurementMessage')

    @classmethod
    def fulfill(cls: Type[_T], actor) -> _T:
        cla = type(actor)
        positional = list(map(attrgetter('name'), filter(lambda f: is_(MISSING, f.default), fields(cls))))
        return cls(**{k: getattr(actor, k).__get__(actor, cla)(  # type: ignore
            new_measurement=not bool(i),
        ) for i, k in enumerate(positional)})


class SettingMessage:
    def _prep(self, actor) -> None:
        if not hasattr(self, '_commands'):
            cls = type(actor)
            # SUPPRESS-LINTER <this should only be used as a dataclass superclass>
            # noinspection PyDataclass
            _fields = list(map(attrgetter('name'), fields(self)))  # type: ignore
            self._commands = [getattr(actor, k).__get__(actor, cls) for k in _fields]
            self._args = [getattr(self, k) for k in _fields]

    def request(self, actor) -> None:
        self._prep(actor)
        actor.write(' ; '.join(self.requests_in_series(actor)))

    def requests_in_series(self, actor):
        self._prep(actor)
        return [command.build(arg) for command, arg in zip(self._commands, self._args)]

    def verify(self, actor) -> None:
        self._prep(actor)
        [command.verify(arg, do_error=True) for command, arg in zip(self._commands, self._args)]


@dataclass
class ChromaTestCondition:
    vdc: float
    vac: float
    frequency: float
    current_limit: float
    phase_on: float = 0.
    phase_off: float = 0.


@dataclass
class OutputOffCondition(SettingMessage):
    output_state: str = 'OFF'
    vac_setting: float = 0.0
    vdc_setting: float = 0.0


@dataclass
class _ChromaTestCondition(SettingMessage):
    _test_con: InitVar[ChromaTestCondition]
    voltage_range: str = 'LOW'
    vdc_plus_limit: float = None  # type: ignore
    vdc_minus_limit: float = None  # type: ignore
    vdc_setting: float = None  # type: ignore
    vac_setting: float = None  # type: ignore
    output_frequency: float = None  # type: ignore
    current_limit: float = None  # type: ignore
    phase_on: float = 0.
    phase_off: float = 0.

    def __post_init__(self, _test_con: ChromaTestCondition) -> None:
        self.vac_setting = _test_con.vac
        self.vdc_setting = _test_con.vdc
        self.output_frequency = _test_con.frequency
        self.current_limit = _test_con.current_limit
        self.phase_on = _test_con.phase_on
        self.phase_off = _test_con.phase_off

        _exp_pk = self.vac_setting * (2 ** .5)
        if (abs(self.vdc_setting) + _exp_pk) > 212.1:
            self.voltage_range = 'HIGH'
            self.vdc_plus_limit = 414.2
            self.vdc_minus_limit = -self.vdc_plus_limit
        else:
            self.voltage_range = 'LOW'
            self.vdc_plus_limit = 212.1
            self.vdc_minus_limit = -self.vdc_plus_limit


@dataclass
class ChromaGenSettings(SettingMessage):
    ocp_delay_s: float = 0.5
    inrush_start_time_ms: float = 0
    inrush_measurement_interval_ms: float = 200
    ac_slew_rate: float = 1200
    dc_slew_rate: float = 1000
    freq_slew_rate: float = 1000


class _RangeState(Enum):
    """
    selects V_out setting command limits
    """
    HIGH = 0
    LOW = auto()


@dataclass
class _Limits:
    """
    constraint class for type checking
    """
    lower: Union[int, float]
    upper: Union[int, float]

    def check(self, arg: Union[int, float]) -> bool:
        return self.lower <= arg <= self.upper


@dataclass
class ChromaMeasurement(MeasurementMessage):
    v_rms: float
    i_rms: float
    pf: float
    cf: float
    inrush: float
    vdc: float
    idc: float
    apparent_p: float = None  # type: ignore
    reactive_p: float = None  # type: ignore
    true_p: float = None  # type: ignore
    pdc: float = None  # type: ignore
    i_pk: float = None  # type: ignore

    def __post_init__(self) -> None:
        self.apparent_p = self.v_rms * self.i_rms
        self.true_p = self.apparent_p * self.pf
        self.reactive_p = abs((self.apparent_p ** 2) - (self.true_p ** 2)) ** .5
        self.i_pk = self.i_rms * self.cf
        self.pdc = self.vdc * self.idc


@dataclass
class NTRRegister(BitField.FromBase10):
    # noinspection PyDataclass
    value: InitVar[int]
    IS_ERROR_STATE: bool = False

    A_TO_D_STAGE_PRO: bool = StatusBit()  # type: ignore
    D_TO_D_STAGE_PRO: bool = StatusBit()  # type: ignore
    OVER_POWER: bool = StatusBit()  # type: ignore
    OVER_TEMP: bool = StatusBit()  # type: ignore
    OUTPUT_SHORT: bool = StatusBit()  # type: ignore
    FAN_FAILURE: bool = StatusBit()  # type: ignore
    OVER_CURRENT: bool = StatusBit()  # type: ignore
    LINE_INPUT_PRO: bool = StatusBit()  # type: ignore
    OVER_VOLTAGE: bool = StatusBit()  # type: ignore


@dataclass
class EventStatusRegister(BitField.FromBase10):
    # noinspection PyDataclass
    value: InitVar[int]
    OP_COMPLETE: bool = StatusBit()  # type: ignore
    QUERY_ERROR: bool = StatusBit(2)  # type: ignore
    DEVICE_ERROR: bool = StatusBit()  # type: ignore
    EXEC_ERROR: bool = StatusBit()  # type: ignore
    COMMAND_ERROR: bool = StatusBit()  # type: ignore
    POWER_ON: bool = StatusBit(7)  # type: ignore


@dataclass
class StatusByteRegister(BitField.FromBase10):
    # noinspection PyDataclass
    value: InitVar[int]
    QUESTIONABLE_STAT: bool = StatusBit(3)  # type: ignore
    MESSAGE_AVAILABLE: bool = StatusBit()  # type: ignore
    EVENT_STATUS_SUM: bool = StatusBit()  # type: ignore
    RQS_MSS_SUM: bool = StatusBit()  # type: ignore


@dataclass
class StatusRegisters(MeasurementMessage):
    ntr_register: NTRRegister
    event_status_register: EventStatusRegister
    status_byte_register: StatusByteRegister


class ValidationError(Exception):
    def __init__(self, command_string: str) -> None:
        self.args = (f'failed to validate command "{command_string}"',)


class _CommandBase:
    command_string: str
    _repr_string: str
    return_format: Optional[type] = None
    exception_class = ValidationError

    def __init__(self, config: Dict[str, Dict[str, Optional[str]]]):
        self.config = config

    def _config_self(self, command_string: str = None, branch: str = None, **kwargs) -> None:
        self.command_string = cast(str, command_string)
        self.branch = _Branch[branch]

    def __set_name__(self, owner, name: str) -> None:
        self.owner = owner
        self.name = name
        self._config_self(**self.config[self.name])
        _display_t = self.return_format.__name__ if hasattr(self.return_format, '__name__') else None
        self._repr_string = f"""{type(self).__name__}({name}, {self.command_string}: {_display_t})"""

    def __get__(self, instance, owner):
        self.instance = instance
        self.owner = owner
        return self

    def _write_only(self, packet: str) -> None:
        self.instance.write(packet)

    def _read_only(self):
        return self.return_format(self.instance.read())

    def __repr__(self) -> str:
        return self._repr_string


class Setting(_CommandBase):
    __return_types_d = {'f': float,
                        'd': int,
                        's': str, }

    def __init__(self, config, callback: bool = False):
        super().__init__(config)
        self.callback = callback

    def _config_self(self, branch: str = None, command_string: str = None, argument_format: str = None,
                     min_val=None, max_val=None, options=None, **kwargs) -> None:
        super()._config_self(command_string=command_string, branch=branch)
        self.argument_format = argument_format
        has_constraint = min_val is not None and max_val is not None
        has_options = options is not None
        if not (has_constraint ^ has_options):
            raise ValidationError(self.command_string)
        self.constraint = _Limits(float(min_val), float(max_val)) if has_constraint else None
        self.options = set(options.split('-')) if has_options else None
        # noinspection SpellCheckingInspection
        self._new_meas_string = self.command_string.replace('FETC', 'MEAS')
        self.argument_format = argument_format
        self.return_format = self.__return_types_d.get(argument_format[-1]) if argument_format else None
        self._last_value = None
        self.query_string = f'{self.command_string}?'

    @register.after('__set_name__')
    def _set_callback_name(self) -> None:
        if self.callback:
            self.callback_name = f'_{self.name}_callback'
            if not callable(getattr(self.owner, self.callback_name, None)):
                raise ChromaPowerSupplyError(f'{self.owner} does not implement callback {self.callback_name}')

    def build(self, arg: ARG_T) -> str:
        if self.constraint is not None and not self.constraint.check(cast(Union[int, float], arg)):
            raise ChromaPowerSupplyError(f'{self}: arg: <{arg}> failed validation')
        if self.options is not None and arg not in self.options:
            raise ChromaPowerSupplyError(f'{self}: arg: <{arg}> failed validation')

        return f'{self.command_string} {self.argument_format % arg}'

    def verify(self, arg: ARG_T, do_error: bool = False) -> bool:
        self._write_only(self.query_string)
        self.instance.info(f'{self}: verifying setting, last value={self._last_value}, arg={arg}')
        success = self._read_only() == arg
        if do_error and not success:
            raise ChromaPowerSupplyError(f'{self}: failed to verify')
        return success

    def __read(self) -> ARG_T:
        self._last_value = self._read_only()
        return self._last_value

    def __call__(self, arg: ARG_T = None) -> Optional[ARG_T]:
        if arg is None:
            self.instance.info(f'{self}: reading setting, last value = {self._last_value}')
            self._write_only(self.query_string)
            return self.__read()
        arg = self.return_format(arg)
        if not (self._last_value == arg and self.verify(arg)):
            self._write_only(self.build(arg))
            self.verify(arg, do_error=True)
            if self.callback:
                getattr(self.instance, self.callback_name)(arg)


class Measurement(_CommandBase):
    return_format = float

    def _config_self(self, command_string: str = None, branch: str = None, **kwargs) -> None:
        super()._config_self(command_string, branch)
        if self.branch != _Branch.MEASURE:
            raise ValidationError(cast(str, command_string))
        self.branch = branch
        self.query_string = f'{self.command_string}?'
        # noinspection SpellCheckingInspection
        self._new_meas_string = self.query_string.replace('FETC', 'MEAS')

    def __call__(self, new_measurement: bool = False):
        if new_measurement:
            self._write_only(self._new_meas_string)
        else:
            self._write_only(self.query_string)
        self.instance.info(f'{self}: requested')
        return self._read_only()


class Command(_CommandBase):
    def __call__(self) -> None:
        return self._write_only(self.command_string)


class Status(_CommandBase):
    def __init__(self, config, status_obj) -> None:
        super().__init__(config)
        self.return_format = status_obj

    def _config_self(self, command_string: str = None, branch: str = None, **kwargs) -> None:
        super()._config_self(command_string, branch)
        self.query_string = f'{self.command_string}?'

    def __call__(self, new_measurement: bool = False):
        _ = new_measurement
        self._write_only(self.query_string)
        self.instance.info('reading status word')
        return self._read_only()


class CommandReader:
    def __init__(self, fp: str) -> None:
        with open(fp) as csv_f:
            self.config = {row['command']: {
                k.strip(): v.strip() or None for k, v in row.items()
            } for row in csv.DictReader(csv_f)}

    def command(self) -> Command:
        return Command(self.config)

    def status(self, status_obj: Type[BitField.FromBase10]) -> Status:
        return Status(self.config, status_obj)

    def setting(self, callback: bool = False) -> Setting:
        return Setting(self.config, callback=callback)

    def measurement(self) -> Measurement:
        return Measurement(self.config)


# noinspection SpellCheckingInspection
@instrument_debug
class ChromaPowerSupply(Serial):
    # TODO check status register endianness
    # TODO check OPC fidelity
    # TODO add inrush delay from test settings command arg to AC measurements or error maybe
    # TODO measure time to execute exposed methods
    # TODO merge leak tester command group idiom to this
    # TODO documentation at least at module level

    # ? W:\TestStation Data Backup\instruments\data\UM-61601~4-acsource-v1.9-102015.pdf
    # ? pg. 67 -> remote operation

    # ? W:\TestStation Data Backup\instruments\data\QSG-61601~4-acsource-v1.0-022010.pdf
    # ? W:\TestStation Data Backup\instruments\data\UM-615,616XX-SoftPanel-v1.6-082013.pdf

    _config = configuration.from_yml(r'W:\Test Data Backup\instruments\config\chroma_power_supply.yml')
    DEVICE_NAME = _config.field(str)
    BAUDRATE = _config.field(int)
    TIMEOUT = _config.field(float)
    TX_WAIT_S = _config.field(float)
    COMMAND_EXEC_WAIT_S = _config.field(float)

    XON_X_OFF = False
    ENCODING = 'utf-8'
    TERM_CHAR = '\r\n'

    _command_config = CommandReader(r'W:\Test Data Backup\instruments\data\Command Source.csv')
    voltage_range = _command_config.setting(True)
    output_state = _command_config.setting()
    output_coupling = _command_config.setting()
    current_limit = _command_config.setting()
    ocp_delay_s = _command_config.setting()
    inrush_start_time_ms = _command_config.setting()
    inrush_measurement_interval_ms = _command_config.setting()
    output_frequency = _command_config.setting()
    _vac_high_range = _command_config.setting()
    _vdc_high_range = _command_config.setting()
    _vac_low_range = _command_config.setting()
    _vdc_low_range = _command_config.setting()
    vac_limit = _command_config.setting()
    vdc_plus_limit = _command_config.setting()
    vdc_minus_limit = _command_config.setting()
    phase_on = _command_config.setting()
    phase_off = _command_config.setting()
    ac_slew_rate = _command_config.setting()
    dc_slew_rate = _command_config.setting()
    freq_slew_rate = _command_config.setting()
    i_rms = _command_config.measurement()
    ipk = _command_config.measurement()
    cf = _command_config.measurement()
    inrush = _command_config.measurement()
    true_power = _command_config.measurement()
    apparent_power = _command_config.measurement()
    reactive_power = _command_config.measurement()
    pf = _command_config.measurement()
    v_rms = _command_config.measurement()
    vdc = _command_config.measurement()
    idc = _command_config.measurement()
    ntr_register = _command_config.status(NTRRegister)
    event_status_register = _command_config.status(EventStatusRegister)
    status_byte_register = _command_config.status(StatusByteRegister)
    clear_protection_latch = _command_config.command()
    clear_registers = _command_config.command()
    vdc_setting: Setting
    vac_setting: Setting

    @register.after('__init__')
    def _set_state_constants(self) -> None:
        self._voltage_range_callback('LOW')

    @register.after('_instrument_setup')
    def _set_output_constant_values(self) -> None:
        # noinspection PyCallingNonCallable
        self.output_coupling('ACDC')
        self.setting(ChromaGenSettings())

    # noinspection PyTypeChecker
    def _voltage_range_callback(self, v_range: str) -> None:
        _range = _RangeState[v_range]
        self.vdc_setting = {_RangeState.HIGH: self._vdc_high_range,
                            _RangeState.LOW: self._vdc_low_range}[_range]
        self.vac_setting = {_RangeState.HIGH: self._vac_high_range,
                            _RangeState.LOW: self._vac_low_range}[_range]

    @proxy.exposed
    def setting(self, condition: Union[SettingMessage],
                delay_override: float = None) -> None:
        for command in condition.requests_in_series(self):
            self.write(command)
        self._instrument_delay(delay_override or self.COMMAND_EXEC_WAIT_S)
        condition.verify(self)

    # noinspection PyCallingNonCallable
    @proxy.exposed
    def output_enable(self) -> None:
        self.clear_protection_latch()
        self.output_state('ON')

    @proxy.exposed
    @register.before('_instrument_cleanup')
    @register.after('_instrument_setup')
    def output_disable(self) -> None:
        self.setting(OutputOffCondition())

    @proxy.exposed
    def operation_completed_bit(self) -> bool:
        self.write('*OPC?')
        return bool(int(self.read()))

    @proxy.exposed
    def check_status_registers(self) -> 'StatusRegisters':
        return StatusRegisters.fulfill(self)

    def _instrument_check(self) -> None:
        ntr = self.check_status_registers().ntr_register
        if ntr:
            raise ChromaPowerSupplyError(ntr)

    def _instrument_debug(self) -> None:
        from time import perf_counter
        for vdc in range(5, 15):
            ti = perf_counter()
            self.write_settings(float(vdc), 0., 60., 0.5)
            self.info('settings', perf_counter() - ti)
            ti = perf_counter()
            self.output_enable()
            self.info('output enable', perf_counter() - ti)
            ti = perf_counter()
            self.info(self.measure())
            self.info('measure', perf_counter() - ti)
            ti = perf_counter()
            self.output_disable()
            self.info('output disable', perf_counter() - ti)

    @proxy.exposed
    def write_settings(self, vdc: float, vac: float, freq: float,
                       i_limit: float, phase_on: float = 0., phase_off: float = 0.) -> None:
        self.setting(_ChromaTestCondition(ChromaTestCondition(vdc, vac, freq, i_limit, phase_on, phase_off)))

    @proxy.exposed
    def measure(self) -> ChromaMeasurement:
        return ChromaMeasurement.fulfill(self)
