import functools
from collections import defaultdict
from collections import deque
from dataclasses import dataclass
from enum import Enum
from functools import reduce
from operator import __or__
from time import perf_counter, sleep, time
from typing import Optional
from typing import Type

import ftd2xx
from ftd2xx.defines import DRIVER_TYPE_D2XX
from ftd2xx.ftd2xx import DeviceError
from funcy.seqs import chunks

from src.instruments.base.instrument import Instrument

__all__ = [
    'FTDI',
    'FTDINoCableError',
    'FTDINotConnectedError',
    'DATA_BITS',
    'PacketCharacteristics',
    'PARITY',
    'Settings',
    'STOP_BITS',
    'Timeouts',
    'WordCharacteristics',
]


class FTDIError(Exception):
    pass


class FTDINotConnectedError(FTDIError):
    pass


class FTDINoCableError(FTDIError):
    pass


class _Enum(Enum):
    def __str__(self) -> str:
        return type(self).__name__ + '.' + self.name

    def __repr__(self) -> str:
        return str(self)


class BUFFER:
    TX = 1
    RX = 2


class PARITY(_Enum):
    NONE = 0
    ODD = 1
    EVEN = 2
    MARK = 3
    SPACE = 4


# noinspection PyPep8Naming
class STOP_BITS(_Enum):
    ONE = 1
    TWO = 2


# noinspection PyPep8Naming
class DATA_BITS(_Enum):
    SEVEN = 7
    EIGHT = 8


class EVENT:
    RX_CHAR = 1
    MODEM_STATUS = 2
    LINE_STATUS = 4


@dataclass(eq=True)
class Timeouts:
    """in ms"""
    read: int
    write: int


@dataclass(eq=True)
class WordCharacteristics:
    data_bits: DATA_BITS
    stop_bits: STOP_BITS
    parity: PARITY


@dataclass
class PacketCharacteristics:
    break_bytes: int
    mab_bytes: int
    line_pause: float


@dataclass(eq=True)
class Settings:
    baudrate: int
    timeouts: Timeouts
    word: WordCharacteristics
    packet: PacketCharacteristics


@dataclass
class Status:
    in_waiting: int
    out_waiting: int
    status: int


def _if_raise(if_e: Type[Exception], then_raise: Type[Exception]):
    def deco(f):
        @functools.wraps(f)
        def inner(self, *args, **kwargs):
            if self.interface is None:
                raise FTDINotConnectedError('FTDI cable is not connected')
            try:
                return f(self, *args, **kwargs)
            except if_e:
                raise then_raise(f'failed in {f.__name__}')

        return inner

    return deco


class FTDI:
    interface: Optional[ftd2xx.FTD2XX]

    CHROMA_STARTUP_S = .7

    def _getter(self, k: str):
        v = getattr(self, f'__{k}', None)
        if v is not None:
            return v
        raise AttributeError(f'{k} not set')

    def _setter(self, k: str, v) -> None:
        setattr(self, f'__{k}', v)

    @_if_raise(DeviceError, FTDINotConnectedError)
    def _set_if_changed(self, f, k: str, v, *args) -> bool:
        try:
            value = self._getter(k)
        except AttributeError:
            pass
        else:
            if self._settings_changed[k]:
                if value is not None and value == v:
                    return True
        f(*args)
        self._setter(k, v)
        self._settings_changed[k] = True
        return False

    @property
    def break_condition(self) -> bool:
        return self._getter('break_condition')

    @break_condition.setter
    def break_condition(self, condition: bool) -> None:
        self._set_if_changed(
            self.interface.setBreakOn if condition else self.interface.setBreakOff,
            'break_condition', condition
        )

    @property
    def baudrate(self) -> int:
        return self._getter('baudrate')

    @baudrate.setter
    def baudrate(self, rate: int) -> None:
        self._set_if_changed(self.interface.setBaudRate, 'baudrate', rate, rate)
        self.break_length = (self._break_bytes / self.baudrate) * self._word_length
        self.mab_length = (self._mab_bytes / self.baudrate) * self._word_length

    @property
    def timeouts(self) -> Timeouts:
        return self._getter('timeouts')

    @timeouts.setter
    def timeouts(self, timeout: Timeouts) -> None:
        self._set_if_changed(self.interface.setTimeouts, 'timeouts', timeout, timeout.read, timeout.write)

    @property
    def word(self) -> WordCharacteristics:
        return self._getter('word_characteristics')

    def _set_word(self, data_bits: int, stop_bits: int, parity: int):
        self.interface.setDataCharacteristics(data_bits, stop_bits, parity)
        self._word_length = 1 + data_bits + stop_bits

    @word.setter
    def word(self, settings: WordCharacteristics) -> None:
        self._set_if_changed(
            self._set_word, 'word_characteristics', settings,
            settings.data_bits.value, settings.stop_bits.value, settings.parity.value
        )

    @property
    def packet(self) -> PacketCharacteristics:
        return self._getter('packet')

    @packet.setter
    def packet(self, settings: PacketCharacteristics) -> None:
        self._break_bytes = settings.break_bytes
        self._mab_bytes = settings.mab_bytes
        # try:
        #     self.break_length = (self._break_bytes / self.baudrate) * self._word_length
        #     print('in packet prop', self.break_length, self._break_bytes, self.baudrate, self._word_length)
        #     self.mab_length = (self._mab_bytes / self.baudrate) * self._word_length
        # except AttributeError:
        #     pass
        self._line_pause = settings.line_pause
        self._setter('packet', settings)

    @property
    def settings(self) -> Settings:
        return self._getter('settings')

    @settings.setter
    def settings(self, settings: Settings) -> None:
        self.timeouts = settings.timeouts
        self.word = settings.word
        self.packet = settings.packet
        self.baudrate = settings.baudrate
        self._setter('settings', settings)

    def __str__(self) -> str:
        name = type(self).__name__
        try:
            return f'{name}({self.settings})'
        except AttributeError:
            return f'{name}()'

    @property
    @_if_raise(DeviceError, FTDINotConnectedError)
    def device_info(self) -> dict:
        return self.interface.getDeviceInfo()

    def __init__(self, instrument: Instrument):  # type: ignore
        self.instrument = instrument
        # noinspection PyProtectedMember
        self.delay_for = self.instrument._instrument_delay
        self.interface = None  # type: ignore
        self.next_tx = time()
        self._settings_changed: defaultdict[str, bool] = defaultdict(lambda: False)

    def close(self) -> None:
        # noinspection PyBroadException
        try:
            self.interface.close()
        except Exception:
            pass

    @property
    def is_connected(self) -> bool:
        try:
            self.open(self.settings)
        except FTDINoCableError:
            return False
        else:
            return True

    def _open(self, settings: Settings):
        self._settings_changed.clear()
        try:
            self.close()
            self.interface = ftd2xx.open(0)
        except DeviceError as e:
            raise FTDINoCableError('No FTDI cable connected') from e
        else:
            self.settings = settings
            self.next_tx = time() + self.instrument.TX_WAIT_S
            self.baud = BaudrateContext(self)

    def open(self, settings: Settings) -> None:
        # noinspection PyBroadException
        try:
            _ = self.status
        except Exception:
            return self._open(settings)
        else:
            self.settings = settings

    def __del__(self) -> None:
        self.close()

    @_if_raise(DeviceError, FTDINotConnectedError)
    def write(self, data: bytes) -> int:
        self.delay_for(0.)
        _t_per_byte = self._word_length / self.baudrate
        _chunks = list(chunks(64, data))
        num_chunks = len(_chunks)
        for i, chunk in enumerate(_chunks):
            chunk_t = len(chunk) * _t_per_byte
            if (i + 1) != num_chunks:
                with TimerContext(chunk_t):
                    self.interface.write(chunk)
            else:
                self.next_tx = time() + self.instrument.TX_WAIT_S + chunk_t
                self.interface.write(chunk)
        return len(data)

    @_if_raise(DeviceError, FTDINotConnectedError)
    def read(self, num_bytes: int) -> bytes:
        self.delay_for(0.)
        rx = self.interface.read(num_bytes, raw=True)
        # self.next_tx = time() + self.instrument.TX_WAIT_S
        self.instrument.debug(f'rx -> {rx}')
        return rx

    def flush(self) -> None:
        while self.out_waiting:
            self.delay_for(0.)

    def send_break(self, duration: float) -> None:
        if duration:
            try:
                # with TimerContext(duration):
                self.break_condition = True
                self.delay_for(duration)
            finally:
                self.break_condition = False

    def clear_read_buffer(self) -> None:
        for _ in range(3):
            in_ = self.in_waiting
            if in_:
                self.read(in_)
                continue
            break
        else:
            raise FTDIError('continuous rx on FTDI')

    def detect_break(self) -> bool:
        is_break = bool(len(self.read(1)))
        if is_break:
            self.clear_read_buffer()
        return is_break

    @_if_raise(DeviceError, FTDINotConnectedError)
    def _reset_buffers(self, *buffers) -> None:
        if not buffers:
            raise ValueError('one or more buffers must be specified')
        self.interface.purge(reduce(__or__, buffers))

    def reset_buffers(self) -> None:
        self._reset_buffers(BUFFER.TX, BUFFER.RX)

    @_if_raise(DeviceError, FTDINotConnectedError)
    def cycle_port(self) -> None:
        self.interface.cyclePort()

    def reset_input_buffer(self) -> None:
        self.clear_read_buffer()
        self._reset_buffers(BUFFER.RX)

    def reset_output_buffer(self) -> None:
        self._reset_buffers(BUFFER.TX)

    @property
    @_if_raise(DeviceError, FTDINotConnectedError)
    def status(self) -> Status:
        return Status(*self.interface.getStatus())

    @property
    def in_waiting(self) -> int:
        return self.status.in_waiting

    @property
    def out_waiting(self) -> int:
        return self.status.out_waiting

    @property
    def event_status(self) -> int:
        return self.status.status

    def send(self, data: bytes) -> None:
        self.delay_for(self.next_tx-time())
        self.send_break(self.break_length)
        with TimerContext(self.mab_length):
            self.reset_input_buffer()
        self.write(data)
        self.instrument.debug(f'tx -> {data}')

    def send_ascii(self, data: str) -> None:
        with self.baud(9600):
            for char in data:
                # sleep(.01)
                self.send(char.encode())
        self.instrument.debug(f'tx -> {data}')
        self.flush()
        self.next_tx = time() + self.instrument.TX_WAIT_S


class TimerContext:
    _timer_f = time
    def __init__(self, te: float) -> None:
        self.te = te

    def __enter__(self) -> 'TimerContext':
        self.tf = self.te + self._timer_f()
        return self

    def __exit__(self, *args):
        sleep(max(0., self.tf - self._timer_f()))


class BaudrateContext:
    def __init__(self, driver: 'FTDI') -> None:
        self.driver = driver

    def __call__(self, baudrate: int) -> 'BaudrateContext':
        self.next = baudrate
        return self

    def __enter__(self) -> 'BaudrateContext':
        self.driver.instrument.info(f'changed baudrate from {self.driver.baudrate} to {self.next}')
        self.next, self.driver.baudrate = self.driver.baudrate, self.next
        return self

    def __exit__(self, *args):
        self.driver.instrument.info(f'changed baudrate from {self.driver.baudrate} to {self.next}')
        self.driver.baudrate = self.next
