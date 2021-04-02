import re
import socket
from dataclasses import dataclass
from dataclasses import field
from dataclasses import fields
from dataclasses import InitVar
from enum import IntEnum
from typing import Callable
from typing import List
from typing import Optional
from typing import Type
from typing import TypeVar
from typing import Union

from src.base import register
from base.concurrency import proxy
from model import configuration
from src.instruments.base.instrument import instrument_debug
from src.instruments.base.instrument import InstrumentError
from src.instruments.base.tcpip import TCPIP

__all__ = [
    'LeakTester',
    'LeakTesterSettings',
    'LeakTesterMeasurement',
    'LeakTesterError',
]


class LeakTesterError(InstrumentError):
    pass


class LeakTestUpdate:
    pass


LT_CONSUMER = Callable[[LeakTestUpdate], ...]


class LeakTesterCommand:
    command_regex = re.compile(r'^S(\w+)%[0-9.]*(\w)')
    type_d = {'f': float, 'd': int, 's': str}
    _arg_T = TypeVar('_arg_T')
    _type: Type[Union[int, float, str]]

    def __init__(self, name: str, string: str) -> None:
        command_string, type_string = self.command_regex.findall(string)[0]
        self.name, self.set_command, self.type = name, string, self.type_d[type_string]
        self._type = self.type_d[type_string]
        self.get = f'R{command_string}'

    def __mod__(self, arg: str) -> str:
        return self.set_command % arg

    def __call__(self, response: str) -> Union[int, float, str]:
        return self.type(response)

    def __repr__(self) -> str:
        return f'COMMAND<{self.name}>'


_result_regex = re.compile(r'(\w+|\w+ \w+)\s+([0-9.-]+)$')
_measurement_regex = re.compile(r'^(\w+|\w+ \w+)\s+([0-9.]+)\s+s\s+([0-9.-]+)$')


class TestType(IntEnum):
    """
    PD only type currently used on the light line
    more types available, see table in documentation below
    """
    # ? W:\TestStation Data Backup\instruments\data\Ethernet-Commands-071113.pdf
    PRESSURE_DECAY = 0


@dataclass
class LeakTesterMeasurement(LeakTestUpdate):
    line_from_socket: InitVar[str]
    step: Optional[str] = None
    is_result: bool = False
    pressure: Optional[float] = None
    t: float = 0.

    @property
    def is_pass(self) -> bool:
        return self.step == 'PASS'

    def __post_init__(self, line_from_socket: str) -> None:
        if _measurement_regex.search(line_from_socket):
            self.step, self.t, self.pressure = _measurement_regex.findall(line_from_socket)[0]

        elif _result_regex.search(line_from_socket):
            self.step, self.pressure = _result_regex.findall(line_from_socket)[0]
            self.is_result = True

        else:
            raise ValueError(f'unable to parse "{line_from_socket}"')

        self.step = self.step.strip().upper()
        self.pressure = float(self.pressure)
        self.t = float(self.t)


class Command:
    __command_regex = re.compile(r'^S(\w+)%[0-9.]*(\w)')
    __type_d = {'f': float, 'd': int, 's': str}

    def __init__(self, command_string: str) -> None:
        self.command_string = command_string
        node_string, type_string = self.__command_regex.findall(command_string)[0]
        self._type = self.__type_d[type_string]
        self.query_string = f'R{node_string}'

    def __set_name__(self, owner, name: str) -> None:
        self.owner = owner
        self.name = name
        self._repr_string = f'{type(self).__name__}({self.name}, {self.command_string}, {self.query_string})'

    def __get__(self, instance, owner):
        self.instance = instance
        self.owner = owner
        return self

    def __get(self):
        self.instance.write(self.query_string)
        try:
            return self._type(self.instance.read())
        except socket.timeout as e:
            raise LeakTesterError(f'{self}: no response to get') from e
        except Exception as e:
            raise LeakTesterError(f'{self}: failed read') from e

    def __set(self, arg):
        try:
            return self.instance.write(self.command_string % arg)
        except Exception as e:
            raise LeakTesterError(f'{self}: failed to write {arg}') from e

    def __call__(self, arg=None):
        if arg is None:
            return self.__get()
        return self.__set(arg)

    def __repr__(self) -> str:
        return self._repr_string


@dataclass(eq=True)
class LeakTesterSettings(LeakTestUpdate):
    test_program_name: str
    test_program_number: int = field(compare=False)
    test_pressure: float
    pressure_max: float
    pressure_min: float
    fast_fill_timer: float
    fill_timer: float
    settle_timer: float
    test_timer: float
    vent_timer: float
    increase_limit: float
    decay_limit: float
    test_volume: float
    test_type: TestType

    @classmethod
    def field_names(cls) -> List[str]:
        return [f.name for f in fields(cls)]

    def __post_init__(self) -> None:
        if not isinstance(self.test_type, TestType):
            self.test_type = TestType(self.test_type)
        self.total_time = sum([
            self.fast_fill_timer, self.fill_timer, self.settle_timer,
            self.test_timer, self.vent_timer,
        ])

    def scale(self, value: LeakTesterMeasurement) -> float:
        """give scaled y-value for a graph"""


@instrument_debug
class LeakTester(TCPIP):
    _config = configuration.from_yml(r'W:\Test Data Backup\instruments\config\leak_tester.yml')
    display_name = _config.field(str)

    IP_ADDRESS = _config.field(str)
    PORT = _config.field(int)
    BUFFER_SIZE = _config.field(int)
    TIMEOUT = _config.field(float)
    TX_WAIT_S = _config.field(float)
    PROCESSING_TIME_S = _config.field(float)
    TEST_PROGRAM_MAP = _config.field(dict)

    ENCODING = 'utf-8'
    TERM_CHAR = ']'
    START_TEST_COMMAND = 'SRP'

    _test_program_name = Command('SPN%s')
    _test_program_number = Command('SCP%d')
    _test_pressure = Command('STP%3.5f')
    # noinspection SpellCheckingInspection
    _pressure_max = Command('SPTP%3.5f')
    # noinspection SpellCheckingInspection
    _pressure_min = Command('SPTM%3.5f')
    _fast_fill_timer = Command('ST3%3.1f')
    _fill_timer = Command('ST4%3.1f')
    _settle_timer = Command('ST5%3.1f')
    _test_timer = Command('ST6%3.1f')
    _vent_timer = Command('ST7%3.1f')
    _increase_limit = Command('SML%3.5f')
    _decay_limit = Command('SMD%3.5f')
    _test_volume = Command('STV%3.5f')
    _test_type = Command('STT%d')

    @register.before('__init__')
    def _leak_test_constants(self) -> None:
        self.test_program_map = {int(k): v for k, v in self.TEST_PROGRAM_MAP.items()}

    def _instrument_check(self) -> None:
        self._test_program_number()

    def __set_test_program_number(self, test_program_number: int) -> None:
        self._test_program_number(test_program_number)
        self._instrument_delay(self.PROCESSING_TIME_S)
        if self._test_program_number() != test_program_number:
            raise LeakTesterError(f'failed to set test program to number {test_program_number}')

    def __run_test(self, test_program: LeakTesterSettings,
                   consumer: LT_CONSUMER = None) -> bool:  # type: ignore
        consumer = consumer if callable(consumer) else self.debug
        consumer(test_program)  # type: ignore

        self.write(self.START_TEST_COMMAND)

        while 1:
            try:
                line = self.read()

            except socket.timeout:
                raise LeakTesterError('no message from leak tester during test')

            else:
                if not line:
                    continue
                meas = LeakTesterMeasurement(line)
                if consumer:
                    consumer(meas)  # type: ignore
                if meas.is_result:
                    return meas.is_pass

    def __get_program_number_from_model_number(self, mn: int) -> int:
        if mn not in self.test_program_map:
            raise LeakTesterError(f'no test program for mn {mn}')
        return self.test_program_map[mn]

    @proxy.exposed
    def get_test_by_number(self, test_number: int) -> LeakTesterSettings:
        self.__set_test_program_number(test_number)
        return LeakTesterSettings(**{k: getattr(self, f'_{k}')() for k in LeakTesterSettings.field_names()})

    @proxy.exposed
    def get_test_from_model_number(self, mn: int) -> LeakTesterSettings:
        return self.get_test_by_number(self.__get_program_number_from_model_number(mn))

    @proxy.exposed
    def run_test_by_number(self, test_number: int, consumer: LT_CONSUMER = None) -> bool:
        return self.__run_test(self.get_test_by_number(test_number), consumer)

    @proxy.exposed
    def run_test_from_model_number(self, mn: int, consumer: LT_CONSUMER = None) -> bool:
        return self.run_test_by_number(self.__get_program_number_from_model_number(mn), consumer)

    @proxy.exposed
    def run_test_by_specification(self, test_program: LeakTesterSettings,
                                  consumer: LT_CONSUMER = None) -> bool:
        test_number = 21
        self.__set_test_program_number(test_number)
        [getattr(self, f'_{k}')(getattr(test_program, k)) for k in test_program.field_names()]

        self._instrument_delay(self.PROCESSING_TIME_S)

        new_program = self.get_test_by_number(test_number)
        if test_program != new_program:
            raise LeakTesterError(f'failed to confirm test from {test_program} to {new_program}')

        return self.__run_test(test_program, consumer)

    def _instrument_debug(self) -> None:
        self.info(self.get_test_by_number(15))
        # spec = LeakTesterSettings(
        #     test_program_name='PRISMA_', test_program_number=15, test_pressure=2.5,
        #     pressure_max=0.75, pressure_min=0.0, fast_fill_timer=2.0, fill_timer=3.5,
        #     settle_timer=13.0, test_timer=15.0, vent_timer=5.0, increase_limit=-0.01,
        #     decay_limit=0.0125, test_volume=575.0, test_type=TestType.PRESSURE_DECAY,
        #     )
        # self.run_test_by_specification(spec)
        # self.run_test_by_number(15)
        # self.run_test(918, on_each)
