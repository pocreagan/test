from collections import Counter
from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from itertools import count
from struct import pack
from struct import unpack
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Set
from typing import Tuple
from typing import Union

from src.base import register
from src.base.actor import configuration
from src.base.actor import proxy
from src.instruments.base.ftdi import DATA_BITS
from src.instruments.base.ftdi import FTDI
from src.instruments.base.ftdi import PacketCharacteristics
from src.instruments.base.ftdi import PARITY
from src.instruments.base.ftdi import Settings
from src.instruments.base.ftdi import STOP_BITS
from src.instruments.base.ftdi import Timeouts
from src.instruments.base.ftdi import WordCharacteristics
from src.instruments.base.instrument import Instrument
from src.instruments.base.instrument import instrument_debug

__all__ = [
    'WETBadResponseError',
    'WETNoResponseError',
    'RS485',
    'RS485Error',
]


def report_result(f: Callable) -> Callable:
    @wraps(f)
    def inner(self, *args, **kwargs):
        value = f(self, *args, **kwargs)
        self.info(f'{f.__name__} -> {value}')
        return value

    return inner


class RS485Error(Exception):
    pass


class WETCommandError(Exception):
    pass


class WETNoResponseError(WETCommandError):
    pass


class WETBadResponseError(WETCommandError):
    pass


class ConfigUpdate:
    pass


@dataclass
class ConfigSetup(ConfigUpdate):
    n: int


@dataclass
class ConfigRegister(ConfigUpdate):
    target: int
    index: int
    payload: int


class FirmwareUpdate:
    pass


@dataclass
class FirmwareSetup(FirmwareUpdate):
    version: int
    n: int


@dataclass
class FirmwareIncrement(FirmwareUpdate):
    i: int


@dataclass
class OrphanCheckResult:
    sn_out_of_range: bool
    no_discovery: bool
    old_firmware: bool
    bootloader: bool


class _CRC:
    def __init__(self) -> None:
        self._array = [
            0, 7, 14, 9, 28, 27, 18, 21, 56, 63, 54, 49, 36, 35, 42, 45,
            112, 119, 126, 121, 108, 107, 98, 101, 72, 79, 70, 65, 84, 83,
            90, 93, 224, 231, 238, 233, 252, 251, 242, 245, 216, 223, 214,
            209, 196, 195, 202, 205, 144, 151, 158, 153, 140, 139, 130, 133,
            168, 175, 166, 161, 180, 179, 186, 189, 199, 192, 201, 206, 219,
            220, 213, 210, 255, 248, 241, 246, 227, 228, 237, 234, 183, 176,
            185, 190, 171, 172, 165, 162, 143, 136, 129, 134, 147, 148, 157,
            154, 39, 32, 41, 46, 59, 60, 53, 50, 31, 24, 17, 22, 3, 4, 13,
            10, 87, 80, 89, 94, 75, 76, 69, 66, 111, 104, 97, 102, 115,
            116, 125, 122, 137, 142, 135, 128, 149, 146, 155, 156, 177,
            182, 191, 184, 173, 170, 163, 164, 249, 254, 247, 240, 229,
            226, 235, 236, 193, 198, 207, 200, 221, 218, 211, 212, 105,
            110, 103, 96, 117, 114, 123, 124, 81, 86, 95, 88, 77, 74, 67,
            68, 25, 30, 23, 16, 5, 2, 11, 12, 33, 38, 47, 40, 61, 58, 51,
            52, 78, 73, 64, 71, 82, 85, 92, 91, 118, 113, 120, 127, 106, 109,
            100, 99, 62, 57, 48, 55, 34, 37, 44, 43, 6, 1, 8, 15, 26, 29, 20,
            19, 174, 169, 160, 167, 178, 181, 188, 187, 150, 145, 152, 159,
            138, 141, 132, 131, 222, 217, 208, 215, 194, 197, 204, 203, 230,
            225, 232, 239, 250, 253, 244, 243,
        ]

    def __call__(self, packet: List[int]) -> int:
        """
        calculate CRC for packet
        """
        _array = self._array
        crc = 0
        for b in packet:
            crc = _array[crc ^ b]
        return crc


CRC = _CRC()
_DMX_ERASE_DMX_PACKET = bytes(([0x0] * 501) + [207, 219, 80, 247, 62, 207, 249, 99, 140, 158, 208, 209, ])
_DTA_BOOT_RESET_PACKET = bytes([
    145, 119, 100, 126, 160, 236, 226, 126, 160, 236, 226,
    126, 160, 236, 226, 126, 160, 236, 226, 126, 160, 236,
    226, 126, 160, 236, 226, 126, 160, 236, 226, 126, 160,
    236, 226, 126, 160, 236, 226, 126, 160, 236, 226, 126,
    160, 236, 226, 126, 160, 236, 226, 126, 160, 236, 226,
    126, 160, 236, 226, 126, 160, 236, 226, 126, 160, 236,
    226, 126, 160, 236, 226, 126, 160, 236, 226, 126, 160,
    236, 226, 126, 160, 236, 226, 126, 160, 236, 226, 126,
    160, 236, 226, 126, 160, 236, 226, 126, 160, 236, 226,
    126, 160, 236, 226, 126, 160, 236, 226, 126, 160, 236,
    226, 126, 160, 236, 226, 126, 160, 236, 226, 126, 160,
    236, 226, 126, 160, 236, 226, 126, 160, 236, 226, 126,
    160, 236, 226, 126, 160, 236, 226, 126, 160, 236, 226,
    126, 160, 236, 226, 126, 160, 236, 226, 126, 160, 236,
    226, 126, 160, 236, 226, 126, 160, 236, 226, 126, 160,
    236, 226, 126, 160, 236, 226, 126, 160, 236, 226, 126,
    160, 236, 226, 126, 160, 236, 226, 126, 160, 236, 226,
    126, 160, 236, 226, 126, 160, 236, 226, 126, 160, 236,
    226, 126, 160, 236, 226, 126, 160, 236, 226, 126, 160,
    236, 226, 126, 160, 236, 226, 126, 160, 236, 226, 126,
    160, 236, 226, 126, 160, 236, 226, 126, 160, 236, 226,
    126, 160, 236, 226, 126, 160, 236, 226, 126, 160, 236,
    226, 126, 160, 236, 226, 126, 160, 236, 226, 126, 160,
    236, 226, 126, 160, 236, 226, 126, 160, 236, 226, 126,
    160, 236, 226, 232, 41, 225, 58
])


class EEPROMTarget(Enum):
    DYNAMIC = 1
    CONFIG = 5
    LEGACY = 7
    COMP = 8


class WETCommandRegister:
    DMX_ADDRESS = EEPROMTarget.CONFIG, 33
    MODEL_NUMBER = EEPROMTarget.CONFIG, 55
    FIRMWARE_VERSION = EEPROMTarget.CONFIG, 56
    SERIAL_NUMBER = EEPROMTarget.CONFIG, 59


class WETCommandDynamicCommand:
    ERASE = EEPROMTarget.DYNAMIC, 0x12, 0xDEADBEEF
    RESET = EEPROMTarget.DYNAMIC, 0x11, 0xCACAFACE
    MUTE = EEPROMTarget.DYNAMIC, 0x0, 0x1
    UNMUTE = EEPROMTarget.DYNAMIC, 0x0, 0x0


@instrument_debug
class RS485(Instrument):
    _config = configuration.from_yml(r'instruments\rs485.yml')

    SERIAL_BREAK_BYTES = _config.field(int)
    MAB_BYTES = _config.field(int)
    TX_WAIT_S = _config.field(float)
    WRITE_TIMEOUT_MS = _config.field(int)
    READ_TIMEOUT_MS = _config.field(int)
    WET_COMMAND_WRITE_ITERATIONS = _config.field(int)
    WET_COMMAND_READ_ATTEMPTS_NO_RESPONSE = _config.field(int)
    WET_COMMAND_READ_ATTEMPTS_BAD_RESPONSE = _config.field(int)
    DISCOVERY_IN_A_ROW_REQUIRED = _config.field(int)
    DISCOVERY_ITERATION_ATTEMPTS = _config.field(int)
    DISCOVERY_MISSES = _config.field(int)
    CHROMA_STARTUP_S = _config.field(float)

    _word_characteristics = WordCharacteristics(
        DATA_BITS.EIGHT, STOP_BITS.TWO, PARITY.NONE
    )
    _baudrate = 250000

    _WET_COMMAND_BROADCAST_ADDRESS = 0
    _WET_COMMAND_RX_PACKET_LENGTH = 9
    _WET_COMMAND_OPCODE_READ = 1
    _WET_COMMAND_OPCODE_WRITE = 0

    _wet_command_address: int

    def _instrument_setup(self) -> None:
        self.ser.open(Settings(
            self._baudrate, Timeouts(
                self.READ_TIMEOUT_MS, self.WRITE_TIMEOUT_MS,
            ), self._word_characteristics, PacketCharacteristics(
                self.SERIAL_BREAK_BYTES, self.MAB_BYTES, self.TX_WAIT_S,
            )
        ))

    def _instrument_cleanup(self) -> None:
        self.ser.close()

    def _instrument_check(self) -> None:
        if not self.ser.is_connected:
            raise RS485Error('no connected')

    def _instrument_debug(self) -> None:
        self.info(self.eeprom_read(*WETCommandRegister.SERIAL_NUMBER))
        self.info(self.eeprom_read(*WETCommandRegister.SERIAL_NUMBER))
        self.info(self.eeprom_read(*WETCommandRegister.SERIAL_NUMBER))

    @register.after('__init__')
    def _rs485_setup(self) -> None:
        self.ser = FTDI(self)
        self._read_error_counter = Counter()
        self._discovery_empties = defaultdict(set)
        self._working_empties = defaultdict(set)

        _old_wet_sn_query = [119, 0, 0, 0, 2, 0, 0, 1]
        _old_wet_sn_query += [CRC(_old_wet_sn_query)]
        self._old_wet_sn_query = bytes(_old_wet_sn_query)

        self._wet_command_read_error_d = {
            WETNoResponseError: self.WET_COMMAND_READ_ATTEMPTS_NO_RESPONSE,
            WETBadResponseError: self.WET_COMMAND_READ_ATTEMPTS_BAD_RESPONSE,
        }
        self.set_broadcast()

    @property
    def address(self) -> int:
        if self._wet_command_address is None:
            raise AttributeError('must specify address')
        return self._wet_command_address

    def set_address(self, setting: int) -> None:
        self._wet_command_address = setting

    def set_broadcast(self) -> None:
        self.set_address(self._WET_COMMAND_BROADCAST_ADDRESS)

    @staticmethod
    def __format_dec(dec: int, num_bytes: int = 4) -> List[int]:
        """
        convert a uint32_t to a reversed list of uint8_t
        """
        return list(map(int, dec.to_bytes(num_bytes, 'little')))

    def __make_packet(self, address: int, target: int, opcode: int, index: int, value: int = None) -> bytes:
        if isinstance(target, EEPROMTarget):
            target = target.value

        payload, opcode = [index], opcode
        if not bool(opcode):
            if value is None:
                raise ValueError('must specify payload if opcode is WRITE')
            payload = [index] + self.__format_dec(value, num_bytes=4)

        size = len(payload) + 1
        packet = [0x77, size] + self.__format_dec(address, num_bytes=3) + \
                 [target * 2 + opcode] + [0x0] * (size % 4) + payload
        return bytes(packet + [CRC(packet)])

    def __read_eeprom(self, num_bytes: int) -> bytes:
        start = self.ser.read(num_bytes)
        if len(start) > 3:
            for i in range(num_bytes - 3):
                if start[i:i + 3] == [0x77, 0x06, 0xEE]:
                    if i:
                        output = start[i:]
                        return output + self.ser.read(i)
                    break
        return start

    def __unmake_packet(self, rx: Optional[bytes]) -> int:
        if not rx:
            self.warning('received nothing')
            raise WETNoResponseError

        _rx = list(unpack('<' + ("B" * len(rx)), rx))
        if len(_rx) != self._WET_COMMAND_RX_PACKET_LENGTH or _rx[0] != 0x77 or _rx[-1] != CRC(_rx[:-1]):
            self.warning(f'received bad packet "{rx}", {rx.hex()}')
            raise WETBadResponseError
        # noinspection SpellCheckingInspection
        return int.from_bytes(pack('<BBBB', *_rx[4:8]), 'little')

    def eeprom_write(self, target: Union[EEPROMTarget, int], index: int, payload: int) -> None:
        _args = self.address, target, self._WET_COMMAND_OPCODE_WRITE, index, payload
        for i in range(self.WET_COMMAND_WRITE_ITERATIONS):
            self.ser.send(self.__make_packet(*_args))
            self.debug(f'eeprom write #{i}: %s %s %02d %08d' % _args[1:])

    def eeprom_read(self, target: Union[EEPROMTarget, int], index: int, *,
                    no_response_attempts: int = None,
                    bad_response_attempts: int = None) -> int:  # type: ignore

        self._read_error_counter.clear()
        error_d = self._wet_command_read_error_d.copy()
        if no_response_attempts is not None:
            error_d[WETNoResponseError] = no_response_attempts
        if bad_response_attempts is not None:
            error_d[WETBadResponseError] = bad_response_attempts

        if isinstance(target, EEPROMTarget):
            target = target.value

        _args = target, self._WET_COMMAND_OPCODE_READ, index
        _log_s = 'eeprom read: %s %s %02d' % _args
        packet = self.__make_packet(self.address, *_args)

        while 1:
            self.ser.send(packet)

            try:
                rx = self.__unmake_packet(self.__read_eeprom(self._WET_COMMAND_RX_PACKET_LENGTH))

            except (WETNoResponseError, WETBadResponseError) as e:
                err_cla = type(e)
                self.warning(f'{_log_s} {err_cla.__name__}')
                self._read_error_counter[err_cla] += 1
                if self._read_error_counter[err_cla] == error_d[err_cla]:
                    raise e

            else:
                self.debug(f'{_log_s} %08d' % rx)
                return rx

    def eeprom_confirm(self, target: int, index: int, value: int) -> bool:
        return self.eeprom_read(target, index) == value

    def __discovery_step(self, bottom, top) -> bool:
        results = []
        packet = [0x77, 0x9, 0xff, 0xff, 0xff, 0x1, 0x0, 0x0, 0x0]
        packet += self.__format_dec(bottom) + self.__format_dec(top)
        packet = bytes(packet + [CRC(packet)])
        for _ in range(self.DISCOVERY_ITERATION_ATTEMPTS):
            for _ in range(self.DISCOVERY_IN_A_ROW_REQUIRED):
                self.ser.send(packet)
                _result = self.ser.detect_break()
                if results and results[-1] ^ _result:
                    continue
                results.append(_result)
            return results[-1]
        return False

    def __discovery_one_sn(self, consumer: Callable = None) -> Optional[int]:
        if self.__discovery_step(2 ** 23, (2 ** 24) - 1):
            self._working_empties.clear()
            bottom = 2 ** 23

            for i, exp in enumerate(range(22, -1, -1)):
                top = bottom + (2 ** exp)
                if (bottom in self._discovery_empties[exp]) or (bottom in self._working_empties[exp]):
                    bottom = top
                    s = 'SKIPPED'

                elif self.__discovery_step(bottom, top):
                    s = 'PRESENT'

                else:
                    self._working_empties[exp].add(bottom)
                    bottom = top
                    s = 'NOT PRESENT'

                consumer((i, bottom, top, s))

            bottom += 1
            if self.__discovery_step(bottom, bottom):
                return bottom

    def __discovery_confirm(self, sn: int) -> bool:
        # noinspection PyBroadException
        try:
            if not self.__discovery_step(sn, sn):
                raise Exception()
            self.set_address(sn)
            if not self.eeprom_confirm(*WETCommandRegister.SERIAL_NUMBER, sn):
                raise Exception()
            self.eeprom_write(*WETCommandDynamicCommand.MUTE)
            if self.__discovery_step(sn, sn):
                raise Exception()

        except Exception:
            self.warning(f'FAILED TO CONFIRM SN {sn}')
            return False

        for exp, value in self._working_empties.items():
            self.discovery_empties[exp] |= value
        self._working_empties.clear()
        self.info('DISCOVERED SN {sn}')
        return True

    @proxy.exposed
    def discovery(self, known_sns: Set = frozenset(), consumer: Callable = None) -> Set[int]:
        self._discovery_empties.clear()
        self.eeprom_write(*WETCommandDynamicCommand.UNMUTE)
        sns = {self.__discovery_confirm(sn) for sn in known_sns}
        number_of_misses = 0
        while number_of_misses < self.DISCOVERY_MISSES:
            if not self.discovery_on_full_range():
                number_of_misses += 1
                continue
            sn = self.__discovery_one_sn(consumer)
            if sn is None or not self.__discovery_confirm(sn):
                number_of_misses += 1
                continue
            sns.add(sn)
        return sns

    @proxy.exposed
    def discovery_on_full_range(self) -> bool:
        return self.__discovery_step(0, (2 ** 32) - 1)

    def __wait_for_reset(self) -> None:
        self._instrument_delay(self.CHROMA_STARTUP_S)

    @proxy.exposed
    def wet_sn_query_any_response(self) -> bool:
        try:
            self.eeprom_read(*WETCommandRegister.SERIAL_NUMBER, bad_response_attempts=1)
        except WETNoResponseError:
            return False
        except WETBadResponseError:
            return True
        return True

    @proxy.exposed
    def wet_responds_to_sn_query(self) -> bool:
        try:
            self.eeprom_read(*WETCommandRegister.SERIAL_NUMBER, bad_response_attempts=1)
        except (WETNoResponseError, WETBadResponseError):
            return False
        else:
            return True

    @proxy.exposed
    def wet_at_least_bootloader(self) -> bool:
        return self.wet_responds_to_sn_query() or self.dta_boot_reset()

    def wet_old_sn_query_any_response(self) -> bool:
        self.ser.send(self._old_wet_sn_query)
        return bool(len(self.ser.read(12)))

    @proxy.exposed
    def orphan_check(self) -> OrphanCheckResult:
        self.set_broadcast()
        return OrphanCheckResult(*[f() for f in (self.discovery_on_full_range,
                                                 self.wet_sn_query_any_response,
                                                 self.wet_old_sn_query_any_response,
                                                 self.dta_boot_reset)])

    @proxy.exposed
    def dmx_erase(self, baudrate: int = None) -> None:
        if baudrate is not None:
            self.info(f'sending DMX erase at {baudrate}baud')
            with self.ser.baud(baudrate):
                return self.ser.send(_DMX_ERASE_DMX_PACKET)

        self.info('sending DMX erase')
        return self.ser.send(_DMX_ERASE_DMX_PACKET)

    @proxy.exposed
    def dmx_control(self, base_value: float = None, is_continuous: bool = False,
                    ch_value_d: Dict[int, float] = None) -> None:

        packet = [0x0] + ([int((base_value or 0.) * 0xFF)] * 512)
        for ch, value in (ch_value_d or {}).items():
            packet[ch] = int(value * 0xFF)
        packet = bytes(packet)

        for i in count(1):
            self.debug(f'sent dmx frame #{i}')
            self.ser.send(packet)
            if not is_continuous:
                break

    @proxy.exposed
    @report_result
    def dta_boot_reset(self) -> bool:
        with self.ser.baud(9600):
            self.info('sending boot reset')
            self.ser.send(_DTA_BOOT_RESET_PACKET)
            return any(self.ser.detect_break() for _ in range(5))

    @proxy.exposed
    @report_result
    def wet_firmware_version(self) -> int:
        return self.eeprom_read(*WETCommandRegister.FIRMWARE_VERSION) >> 8

    @proxy.exposed
    @report_result
    def wet_serial_number(self) -> int:
        return self.eeprom_read(*WETCommandRegister.SERIAL_NUMBER)

    @proxy.exposed
    @report_result
    def wet_model_number(self) -> int:
        return self.eeprom_read(*WETCommandRegister.MODEL_NUMBER)

    @proxy.exposed
    @report_result
    def dta_is_programmed_correctly(self, version: int):
        try:
            _ = self.wet_serial_number()
        except (WETNoResponseError, WETBadResponseError):
            return False
        else:
            return self.wet_firmware_version() == version

    @proxy.exposed
    def send_pixie2_command(self, ch_on: int) -> None:
        n = 0 if not ch_on else 1 << (ch_on - 1)
        self.send_ch_mask_raw(n)

    @proxy.exposed
    def send_ch_mask_raw(self, mask: int) -> None:
        self.ser.send_ascii(f'p{mask}\n')

    @proxy.exposed
    def dta_erase_and_confirm(self):
        self.dmx_erase()
        self.__wait_for_reset()
        return self.dta_boot_reset()

    @proxy.exposed
    def dta_program_firmware(self, packets: List[bytes], version,
                             consumer: Callable[..., None] = None) -> None:
        consumer = consumer if callable(consumer) else self.info

        self.info(f'programming FW version={version}')
        consumer(FirmwareSetup(version, len(packets)))

        with self.ser.baud(9600):
            for i, chunk in enumerate(packets):
                self.ser.send(chunk)
                consumer(FirmwareIncrement(i))

        self.__wait_for_reset()
        self.info(f'programming FW complete')

    def __wet_unit_identity(self, f, sn: int, mn: int):
        _ = self
        return f(*WETCommandRegister.SERIAL_NUMBER, sn) and f(*WETCommandRegister.MODEL_NUMBER, mn)

    @proxy.exposed
    def wet_write_unit_identity(self, sn: int, mn: int) -> None:
        """
        write SN and MN to unit's EEPROM
        """
        self.__wet_unit_identity(self.eeprom_write, sn, mn)

    @proxy.exposed
    def wet_confirm_unit_identity(self, sn: int, mn: int) -> bool:
        return self.__wet_unit_identity(self.eeprom_confirm, sn, mn)

    @proxy.exposed
    def wet_is_communicating(self) -> bool:
        try:
            _ = self.eeprom_read(*WETCommandRegister.SERIAL_NUMBER)
        except (WETNoResponseError, WETBadResponseError):
            return False
        else:
            return True

    @proxy.exposed
    def wet_send_reset(self, wait_after: bool = True) -> None:
        self.eeprom_write(*WETCommandDynamicCommand.RESET)
        if wait_after:
            self.__wait_for_reset()

    @proxy.exposed
    def wet_configure(self, config: Dict[Tuple[int, int], int],
                      consumer: Callable[[ConfigUpdate], None] = None,
                      read_first: bool = True) -> None:
        consumer = consumer if callable(consumer) else self.info

        self.info('configuration begun')

        consumer(ConfigSetup(len(config) * 2))
        already_good = set()
        try:
            for (target, index), payload in config.items():
                if read_first and self.eeprom_confirm(target, index, payload):
                    already_good.add((target, index))
                else:
                    self.eeprom_write(target, index, payload)
                consumer(ConfigRegister(target, index, payload))

            for (target, index), payload in config.items():
                if (target, index) not in already_good:
                    if not self.eeprom_confirm(target, index, payload):
                        raise RS485Error(f'failed to confirm {target} {index} {payload}')
                consumer(ConfigRegister(target, index, payload))

        except (WETNoResponseError, WETBadResponseError) as e:
            raise RS485Error('comm failure in configuration') from e

        self.info('configuration complete')
