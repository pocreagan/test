import functools
from dataclasses import dataclass
from enum import auto
from enum import Enum
from time import time
from typing import Callable
from typing import Type
from typing import TypeVar
from typing import Union

from serial import SerialTimeoutException

from src.base import register
from src.base.actor import proxy
from src.base.actor import configuration
from src.instruments.base.instrument import instrument_debug
from src.instruments.base.instrument import InstrumentError
from src.instruments.base.serial import Serial

__all__ = [
    'Cirris',
    'CirrusTestProgram',
    'CirrusTestType',
    'CirrisError',
]

_ARG_T = TypeVar('_ARG_T', bound=Callable)


class CirrisError(InstrumentError):
    pass


class CirrusTestType(Enum):
    LV_HV = 0
    LV = auto()
    HV = auto()


@dataclass
class CirrusTestProgram:
    program_number: int
    test_type: CirrusTestType
    duration: float


class Command:
    instance: 'Cirris'
    owner: Type['Cirris']
    name: str

    def __init__(self, string: str) -> None:
        self.command_string = string

    def __set_name__(self, owner, name) -> None:
        self.owner = owner
        self.name = name
        self._repr_string = f'Command[{type(self).__name__}]({name}, {self.command_string})'

    def __get__(self, instance, owner):
        self.instance = instance
        self.owner = owner
        return self

    def execute(self, packet: str):
        raise NotImplementedError

    @functools.singledispatch
    def _condition_parameter(self, value):
        return value

    @_condition_parameter.register
    def _(self, value: Enum) -> int:
        return value.value

    @_condition_parameter.register
    def _(self, value: bool) -> str:
        return 'T' if value else 'F'

    def make_parameter(self, k: str, value):
        if k not in self.command_string:
            raise ValueError(f'kwarg key {k} not present in command {self.command_string}')
        return self._condition_parameter(value)

    def __call__(self, **kwargs):
        return self.execute(self.command_string.format(**{
            k: self.make_parameter(k, v) for k, v in kwargs.items()
        }))

    def __repr__(self):
        return self._repr_string


class NoReturn(Command):
    def execute(self, packet: str):
        self.instance.write(packet)


class ReturnStatus(Command):
    def execute(self, packet: str):
        self.instance.write(packet)
        if self.instance.read() == 'T':
            return self.instance.get_status()
        raise CirrisError(f'failed to execute {self}')


class ReturnBool(Command):
    def execute(self, packet: str):
        self.instance.write(packet)
        return self.instance.read() == 'T'


# noinspection SpellCheckingInspection
@instrument_debug
class Cirris(Serial):
    """
    get currently programmed tests as a command_string
    run specific test and return bool P/F
    """

    # ? W:\TestStation Data Backup\instruments\data\Cirris TestStation Language 2019.3.1.pdf

    _config = configuration.from_yml(r'W:\Test Data Backup\instruments\config\cirrus.yml')
    DEVICE_NAME = _config.field(str)
    BAUDRATE = _config.field(int)
    TIMEOUT = _config.field(float)
    RX_ACCUMULATION_TIME_S = _config.field(float)

    XON_X_OFF = False
    ENCODING = 'utf-8'
    TERM_CHAR = '\r\n'

    _start_test = NoReturn('CHTE({test_prog} {test_type})')
    _get_status = NoReturn('STAT')
    _remote_mode = NoReturn('')

    _fail_sound = ReturnBool('SOUN(3)')
    _pass_sound = ReturnBool('SOUN(5)')
    # TODO: do we need to turn the sound off or set its duration?
    _is_cable_present = ReturnBool('PRES')
    _calculate_fault_location = ReturnBool('FAUL({do_calculate})')
    _local_mode = ReturnBool('EXIT')
    _self_test = ReturnBool('SELF')
    _delay_test_start = ReturnBool('TDEY({setting})')

    _list_tests = ReturnStatus('M_LI')

    def get_status(self) -> Union[bool, str]:
        self._get_status()
        rx = self.read()
        if rx in {'T', 'F'}:
            return rx == 'T'
        return rx

    @proxy.exposed
    def is_cable_present(self) -> bool:
        return self._is_cable_present()

    @proxy.exposed
    def get_tests(self) -> str:
        result = self._list_tests()
        if not result:
            raise CirrisError('failed to retrieve test list')
        return result

    @proxy.exposed
    def run_test(self, test_program: CirrusTestProgram) -> Union[str, bool]:
        # TODO: parse failing result string
        self._start_test(test_prog=test_program.program_number, test_type=test_program.test_type.value)
        tf = time() + test_program.duration
        while 1:

            try:
                result = self.read()

            except SerialTimeoutException as e:
                if time() > tf:
                    raise CirrisError('failed to get test result') from e

            else:
                if result == 'T':
                    return True

                return result

    @register.after('_instrument_setup')
    def _cirris_setup(self) -> None:
        self._remote_mode()
        if not self._calculate_fault_location(do_calculate=False):
            raise CirrisError('faild to disable fault location calc')
        if not self._delay_test_start(setting=False):
            raise CirrisError('failed to disable test start delay')

    @register.before('_instrument_cleanup')
    def _cirris_cleanup(self) -> None:
        self._local_mode()

    def _instrument_check(self) -> None:
        self.get_tests()

    def _instrument_debug(self) -> None:
        [self.info(line) for line in self.get_tests().splitlines()]


if __name__ == '__main__':
    Cirris.instrument_debug(with_comm=False)
