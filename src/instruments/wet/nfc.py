from collections import deque
from typing import List
from typing import Optional

from src.base import register
from src.base.actor import proxy
from src.base.actor import configuration
from src.instruments.base.instrument import instrument_debug
from src.instruments.base.instrument import InstrumentError
from src.instruments.base.serial import Serial

__all__ = [
    'NFC',
    'NFCError',
]


class NFCError(InstrumentError):
    pass


@instrument_debug
class NFC(Serial):
    _config = configuration.from_yml(r'instruments\nfc_probe.yml')
    display_name = _config.field(str)
    TIMEOUT = _config.field(float)
    TX_WAIT_S = _config.field(float)
    COMMAND_RETRIES = _config.field(int)
    ACTION_RETRIES = _config.field(int)
    READ_BLOCK_ATTEMPTS = _config.field(int)
    READ_BLOCK_SUCCESSIVE = _config.field(int)
    REDUNDANT_ATTEMPTS = _config.field(int)
    WRITE_BLOCKS = _config.field(tuple)
    SN_BLOCKS = _config.field(dict)
    MN_BLOCKS = _config.field(dict)

    # DEVICE_NAME = "Arduino LilyPad USB"
    HWID = r'5&33EB7B70&0&7'
    BAUDRATE = 57600
    XON_X_OFF = False
    ENCODING = 'utf-8'
    TERM_CHAR = '\n'

    class __Commands:
        is_present = "X"
        read_uid = "U"
        set_block = "B%02x"
        write_block = "W%08x"
        read_block = "R"

    BLOCKS: List[List[int]]

    @register.before('__init__')
    def _make_nfc_attrs(self) -> None:
        self.BLOCKS = [[v for k, v in d.items() if k in self.WRITE_BLOCKS] for d in
                       (self.SN_BLOCKS, self.MN_BLOCKS)]
        if not all(self.BLOCKS):
            raise AttributeError('must specify at least one of [new, old] in write_blocks')
        self._read_tail = deque(maxlen=self.READ_BLOCK_SUCCESSIVE)

    def _command(self, command: str, arg: Optional[int]) -> str:
        if '%' in command:
            if arg is None:
                raise NFCError(f'{command} takes no argument')
            command = command % arg
        for i in range(self.COMMAND_RETRIES):
            self.proxy_check_cancelled()
            self.write(command)
            rx = self.read()
            if rx:
                return rx
        raise NFCError(f'no response to command "{command}"')

    def _action(self, command_string, arg: Optional[int] = None):
        for i in range(self.ACTION_RETRIES):
            # noinspection PyBroadException
            try:
                return self._command(command_string, arg)
            except NFCError:
                self.instrument_setup()
                continue
        raise NFCError(f'failed: {command_string}({arg})')

    def _set_block(self, index: int) -> None:
        if not index == int(self._action(self.__Commands.set_block, index)[:-1], 16):
            raise NFCError(f'failed to set block to {index}')

    def _write_block(self, payload: int) -> None:
        if not 'Y' == self._action(self.__Commands.write_block, payload):
            raise NFCError(f'failed to write block to {payload}')

    def _read_block(self) -> int:
        for _ in range(self.REDUNDANT_ATTEMPTS):
            self._read_tail.clear()
            for _ in range(self.READ_BLOCK_ATTEMPTS):
                value = int(self._action(self.__Commands.read_block)[:-1], 16)
                self._read_tail.append(value)
                if self._read_tail.count(value) == self.READ_BLOCK_SUCCESSIVE:
                    return value
        raise NFCError('inconsistent _read_block iterations')

    @proxy.exposed
    def read_register(self, index: int):
        self._set_block(index)
        return self._read_block()

    @proxy.exposed
    def write_register(self, index: int, payload: int):
        self._set_block(index)
        self._write_block(payload)
        if self._read_block() != payload:
            raise NFCError(f'failed to confirm write_register({index}, {payload})')

    @proxy.exposed
    def is_present(self):
        return 'Y' == self._action(self.__Commands.is_present)

    @proxy.exposed
    def read_uid(self):
        return self._action(self.__Commands.read_uid)

    @proxy.exposed
    def write_unit_identity(self, sn: int, mn: int):
        for blocks, payload in zip(self.BLOCKS, (sn, mn)):
            blocks: List[int]
            [self.write_register(block, payload) for block in blocks]

    @proxy.exposed
    def get_registers(self):
        response = {}
        for blocks in self.BLOCKS:
            for index in blocks:
                response[index] = self.read_register(index)
        return response

    def _instrument_check(self) -> None:
        self._action(self.__Commands.is_present)

    @proxy.exposed
    def test(self) -> None:
        [self.info(f'is_present = {self.is_present()}') for _ in range(25)]

    def _instrument_debug(self) -> None:
        self.test()
