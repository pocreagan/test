from typing import Callable
from typing import Optional

import serial
from serial.serialutil import SerialException
from serial.tools.list_ports import comports
from serial.tools.list_ports_common import ListPortInfo

from src.instruments.base.instrument import StringInstrument

__all__ = [
    'Serial',
]


class Serial(StringInstrument):
    def _instrument_check(self) -> None:
        raise NotImplementedError

    def _instrument_debug(self) -> None:
        raise NotImplementedError

    DEVICE_NAME: str
    BAUDRATE: int
    TIMEOUT: float
    XON_X_OFF: bool
    PORT: Optional[str] = None

    interface: serial.Serial

    def __make_find_func(self) -> Callable[[ListPortInfo], bool]:
        _hwid, _dev_name = [getattr(self, k, None) for k in ['HWID', 'DEVICE_NAME']]
        if _hwid is None:
            return lambda comport: _dev_name in comport.description
        elif _dev_name is None:
            return lambda comport: _hwid in comport.hwid
        raise AttributeError('need to declare hwid or device name')

    def __find_fd(self) -> None:
        find_function = self.__make_find_func()
        for comport in comports():
            self.info(comport.hwid, comport.description)
            if find_function(comport):
                self.debug(f'{comport.description} | {comport.hwid} | {comport.device}')
                return comport.device
        raise SerialException('could not find a com port matching data in config')

    def _instrument_setup(self) -> None:
        self.PORT = self.PORT or self.__find_fd()
        self.interface = serial.Serial(
            port=self.PORT,
            baudrate=self.BAUDRATE,
            timeout=self.TIMEOUT,
            xonxoff=self.XON_X_OFF
        )

    def _instrument_cleanup(self) -> None:
        self.interface.close()

    def _send(self, data: str) -> None:
        self.interface.reset_input_buffer()
        self.interface.write(self._prep_command(data))
        self.interface.flush()

    def _receive(self, n: int = None) -> str:
        return self._strip_command(self.interface.readline() if n is None else self.interface.read(n))
