from dataclasses import dataclass
from enum import Enum
from time import time
from typing import Callable

try:
    from parse import compile as compile_parser  # type: ignore
except ImportError:
    raise ImportError('pip install parse')

from src.base import register
from base.concurrency import proxy
from model import configuration
from src.instruments.base.instrument import InstrumentError
from src.instruments.base.instrument import instrument_debug
from src.instruments.base.serial import Serial

__all__ = [
    'HipotTester',
    'HipotMeasurement',
    'HipotProgram',
    'HipotTesterError',
]

_test_settings_proto = '{test_type},{voltage:f}kV,H={upper:f}mA,L={lower:f}mA,R={ramp_t:f}S,T={test_t:f}S'
_test_measurement_proto = '{},{test_status} ,{voltage:f}kV,{current:f} mA ,{step}={time_elapsed:f}S'


class HipotTesterError(InstrumentError):
    pass


class HipotUpdate:
    pass


HIPOT_CONSUMER = Callable[[HipotUpdate], None]


class StringEnum(Enum):
    @property
    def string(self) -> str:
        return self.name.split('.')[-1]

    def __repr__(self) -> str:
        return f'{type(self).__name__}.{self.name}'


class TestType(StringEnum):
    DCW = 0
    ACW = 1


class ArcMode(StringEnum):
    OFF = 0
    ON_CONT = 1
    ON_STOP = 2


class GroundMode(StringEnum):
    ON = 0
    OFF = 1


class Frequency(Enum):
    NONE = 0
    FIFTY = 1
    SIXTY = 2

    def to_number(self) -> int:
        return 50 if self == Frequency.FIFTY else 60

    @classmethod
    def from_number(cls, n: int) -> 'Frequency':
        return cls.FIFTY if n == 50 else cls.SIXTY

    def __repr__(self) -> str:
        return f'{type(self).__name__}.{self.name}'


@dataclass(eq=True)
class HipotProgram(HipotUpdate):
    ramp_t: float = None  # type: ignore
    test_t: float = None  # type: ignore
    voltage: float = None  # type: ignore
    upper: float = None  # type: ignore
    lower: float = None  # type: ignore
    ref_current: float = None  # type: ignore
    arc_current: float = None  # type: ignore
    test_type: TestType = None  # type: ignore
    frequency: Frequency = None  # type: ignore
    arc_mode: ArcMode = None  # type: ignore
    ground_mode: GroundMode = None  # type: ignore
    is_ac: bool = None  # type: ignore
    total_t: float = None  # type: ignore

    def __post_init__(self):
        self.total_t = self.ramp_t + self.test_t
        if not isinstance(self.test_type, TestType):
            self.test_type = TestType[self.test_type]
        self.is_ac = self.test_type == TestType.ACW


@dataclass
class HipotMeasurement(HipotUpdate):
    test_status: str = None  # type: ignore
    step: str = None  # type: ignore
    voltage: float = None  # type: ignore
    current: float = None  # type: ignore
    time_elapsed: float = None  # type: ignore
    total_time: float = None  # type: ignore

    def __post_init__(self):
        self.total_time = self.time_elapsed


class Command:
    def __init__(self, command_string: str, response_parse: str = None) -> None:
        self.command_string = command_string
        self.response_parse = compile_parser(response_parse) if response_parse else None
        self.has_args = '%' in self.command_string

    def __set_name__(self, _, name):
        self.name = name
        self._repr_string = f'{type(self).__name__}({self.name}, {self.command_string})'
        self.is_setter = self.name[:5] == '_set_'

    def __get__(self, instance, _):
        self.instance = instance
        return self

    def __make_packet(self, arg=None) -> str:
        if self.has_args:
            if arg is None:
                raise ValueError(f'{self} requires an argument')
            return self.command_string % arg
        return self.command_string

    def __get_response(self):
        rx = self.instance.read()
        if rx == '':
            raise HipotTesterError('{self} received no response')

        result = self.response_parse.parse(rx)
        if result is not None:
            result = result.named  # type: ignore

            if not result:
                return True

            if len(result) == 1:
                return list(result.values())[0]

            return result

        raise HipotTesterError(
            f'{self} failed to parse "{rx}" with "{self.response_parse}'
        )

    def __call__(self, arg=None):
        for i in range(2):
            packet = self.__make_packet(arg)
            self.instance.write(packet)
            if self.response_parse:
                return self.__get_response()

            elif self.is_setter and not self.instance.ERROR_CHECK_ONLY_AFTER_LOAD:
                try:
                    return self.instance.check_for_error_code(packet)

                except HipotTesterError:
                    if not i:
                        raise

            else:
                return


@instrument_debug
class HipotTester(Serial):
    # ? W:\TestStation Data Backup\instruments\data\GPT-9800-m.pdf
    _config = configuration.from_yml(r'W:\Test Data Backup\instruments\config\hipot_tester.yml')
    display_name = _config.field(str)

    TEST_DURATION_MARGIN = _config.field(float)
    DELAY_BETWEEN_MEASUREMENTS_S = _config.field(float)
    HWID = _config.field(str)
    BAUDRATE = _config.field(int)
    TIMEOUT = _config.field(float)
    TX_WAIT_S = _config.field(float)
    ERROR_CHECK_ONLY_AFTER_LOAD = _config.field(bool)

    XON_X_OFF = False
    ENCODING = 'utf-8'
    TERM_CHAR = '\r\n'

    _get_identify = Command('*IDN?', '{}GPT{}')
    _get_errors = Command('SYST:ERR ?', '{errors}')  # returns error strings from pg.136 of the docs
    _clear_errors = Command('*CLS')  # clears internal registers
    _get_measurement = Command('MEAS ?', _test_measurement_proto)
    _get_test_settings = Command('MANU%d:EDIT:SHOW ?', _test_settings_proto)
    _start_test = Command('FUNC:TEST ON')
    _stop_test = Command('FUNC:TEST OFF')

    # for DC and AC
    _set_to_manual = Command('MAIN:FUNC MANU')
    _set_test_type = Command('MANU:EDIT:MODE %s')  # {ACW, DCW}
    _set_ramp_t = Command('MANU:RTIM %f')  # 0.1~999.9 seconds
    _set_test_number = Command('MANU:STEP %d')  # 1-100
    _set_arc_mode = Command('MANU:UTIL:ARCM %s')  # {OFF, ON_CONT, ON_STOP}
    _set_ground_mode = Command('MANU:UTIL:GROUNDMODE %s')  # {ON, OFF}

    _get_test_number = Command('MANU:STEP ?', '{test_program:d}')
    _get_arc_mode = Command('MANU:UTIL:ARCM ?', 'ARC {arc_mode}')
    _get_ground_mode = Command('MANU:UTIL:GROUNDMODE ?', '{gound_mode}')

    # for AC
    _set_ac_voltage = Command('MANU:ACW:VOLT %.3f')  # 0.1-5.0kV
    _set_ac_upper = Command('MANU:ACW:CHIS %f')  # 0.001 ~ 042.0mA
    _set_ac_lower = Command('MANU:ACW:CLOS %f')  # 0.000 ~ 041.9mA
    _set_ac_test_t = Command('MANU:ACW:TTIM %f')  # 0.5 ~ 999.9 seconds
    _set_ac_frequency = Command('MANU:ACW:FREQ %d')  # {50, 60} Hz
    _set_ac_ref_current = Command('MANU:ACW:REF %f')  # 0.000 ~ 041.9mA
    _set_ac_arc_current = Command('MANU:ACW:ARCC %f')  # 0.000 ~ 080.0mA (<2x upper)

    _get_ac_frequency = Command('MANU:ACW:FREQ ?', '{frequency:d} Hz')
    _get_ac_ref_current = Command('MANU:ACW:REF ?', '{ref_current:f}mA')
    _get_ac_arc_current = Command('MANU:ACW:ARCC ?', '{arc_current:f}mA')

    # for DC
    _set_dc_voltage = Command('MANU:DCW:VOLT %f')  # 0.100 ~ 6.100kV
    _set_dc_upper = Command('MANU:DCW:CHIS %f')  # 0.001 ~ 11.00mA
    _set_dc_lower = Command('MANU:DCW:CLOS %f')  # 0.000 ~ 010.9mA
    _set_dc_test_t = Command('MANU:DCW:TTIM %f')  # 0.5 ~ 999.9 seconds
    _set_dc_ref_current = Command('MANU:DCW:REF %f')  # 000.0 ~ 010.9mA
    _set_dc_arc_current = Command('MANU:DCW:ARCC %f')  # 000.0 ~ 22.00mA

    _get_dc_ref_current = Command('MANU:DCW:REF ?', '{ref_current:f}mA')
    _get_dc_arc_current = Command('MANU:DCW:ARCC ?', '{arc_current:f}mA')

    _still_testing_steps = {'TEST', 'VIEW'}

    @register.after('_instrument_setup')
    def _hipot_setup(self) -> None:
        self._clear_errors()
        self._set_to_manual()

    def _instrument_check(self) -> None:
        self._get_identify()

    def check_for_error_code(self, packet: str) -> None:
        errors = self._get_errors()
        if errors and (errors != '0,No Error'):
            self._clear_errors()
            raise HipotTesterError(f'got error codes "{errors}" after {packet}')

    def set_test_program(self, test_program: int) -> None:
        self._set_test_number(test_program)
        if test_program != self._get_test_number():
            raise HipotTesterError(f'failed to set test program to {test_program}')

    def __run_test(self, test_specs: HipotProgram, consumer: HIPOT_CONSUMER = None) -> bool:  # type: ignore
        consumer = consumer if callable(consumer) else self.debug
        consumer(test_specs)  # type: ignore
        self._start_test()
        max_test_len = test_specs.total_t + self.TEST_DURATION_MARGIN  # type: ignore
        tf = max_test_len + time()  # type: ignore
        last_t, do_delay, ramp_te = None, True, 0.

        while 1:
            self._instrument_delay(self.DELAY_BETWEEN_MEASUREMENTS_S if do_delay else 0.)
            do_delay = True

            try:
                meas = HipotMeasurement(**self._get_measurement())  # type: ignore

            except HipotTesterError as e:
                do_delay = False
                if time() > tf:
                    raise HipotTesterError(f'failed to receive test result after {max_test_len}') from e

            else:
                if meas.time_elapsed != last_t:
                    last_t = meas.time_elapsed
                    if meas.step == 'R':
                        ramp_te = last_t

                    elif meas.step == 'T':
                        meas.total_time += ramp_te

                    consumer(meas)

                    if meas.test_status not in self._still_testing_steps:
                        return meas.test_status == 'PASS'

    @proxy.exposed
    def get_test_program(self, test_number: int) -> HipotProgram:
        test_program = HipotProgram(**self._get_test_settings(test_number))  # type: ignore

        test_program.arc_mode = ArcMode[self._get_arc_mode()]
        test_program.ground_mode = GroundMode[self._get_ground_mode()]

        k = 'ac' if test_program.is_ac else 'dc'
        for attr in ('ref_current', 'arc_current'):
            setattr(test_program, attr, getattr(self, f'_get_{k}_{attr}')())

        if test_program.is_ac:
            _freq: int = self._get_ac_frequency()  # type: ignore
            test_program.frequency = Frequency.from_number(_freq)
        else:
            test_program.frequency = Frequency.NONE

        return test_program

    @proxy.exposed
    def run_test_by_number(self, test_number: int, consumer: HIPOT_CONSUMER = None) -> bool:
        self._clear_errors()
        self.set_test_program(test_number)
        test_program = self.get_test_program(test_number)

        return self.__run_test(test_program, consumer)

    @proxy.exposed
    def run_test_by_specification(self, test_program: HipotProgram, consumer: HIPOT_CONSUMER = None) -> bool:
        test_number = 21
        self._clear_errors()
        self.set_test_program(test_number)
        self._set_test_type(test_program.test_type.name)
        self._set_arc_mode(test_program.arc_mode.name)
        self._set_ground_mode(test_program.ground_mode.name)
        self._set_ramp_t(test_program.ramp_t)

        k = 'ac' if test_program.is_ac else 'dc'
        for attr in ('test_t', 'voltage', 'upper', 'lower', 'ref_current', 'arc_current'):
            getattr(self, f'_set_{k}_{attr}')(getattr(test_program, attr))

        if test_program.is_ac:
            self._set_ac_frequency(test_program.frequency.to_number())

        if not test_program == self.get_test_program(test_number):
            raise HipotTesterError(f'failed to confirm test programming from spec {test_program}')

        if self.ERROR_CHECK_ONLY_AFTER_LOAD:
            self.check_for_error_code('checking after load')

        return self.__run_test(test_program, consumer)

    def _instrument_debug(self) -> None:
        # ac_spec = HipotProgram(
        #     ramp_t=3.0, test_t=1.0, voltage=0.6, upper=1.0,
        #     lower=0.0, ref_current=0.0, arc_current=1.0, test_type=TestType.ACW,
        #     frequency=Frequency.SIXTY, arc_mode=ArcMode.ON_STOP,
        #     ground_mode=GroundMode.ON, is_ac=True, total_t=4.0
        # )
        dc_spec = HipotProgram(
            ramp_t=10.0, test_t=3.3, voltage=1.5, upper=0.1,
            lower=0.0, ref_current=0.0, arc_current=1.0, test_type=TestType.DCW,
            frequency=Frequency.NONE, arc_mode=ArcMode.ON_STOP,
            ground_mode=GroundMode.ON, is_ac=False, total_t=13.3
        )
        self.run_test_by_number(2)
        self.run_test_by_specification(dc_spec)
