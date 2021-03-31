from socket import AF_INET
from socket import SOCK_STREAM
from socket import socket
from socket import timeout

from src.instruments.base.instrument import StringInstrument

__all__ = [
    'TCPIP',
]


# noinspection SpellCheckingInspection
class TCPIP(StringInstrument):
    def _instrument_check(self) -> None:
        raise NotImplementedError

    def _instrument_debug(self) -> None:
        raise NotImplementedError

    TIMEOUT: float
    IP_ADDRESS: str
    PORT = int
    BUFFER_SIZE: int

    interface: socket

    def __make_socket_fd(self) -> None:
        try:
            self.reader.close()
        except AttributeError:
            pass
        self.reader = self.interface.makefile()

    def _instrument_setup(self) -> None:
        self.interface = socket(AF_INET, SOCK_STREAM)
        self.interface.connect((self.IP_ADDRESS, self.PORT))
        self.interface.settimeout(self.TIMEOUT)
        self.__make_socket_fd()

    def _instrument_cleanup(self) -> None:
        self.interface.close()

    def _send(self, data: str) -> None:
        self.interface.send(self._prep_command(data))

    def _receive(self, **kwargs) -> str:  # type: ignore
        try:
            return self.reader.readline().strip()
        except OSError:
            self.__make_socket_fd()
            raise timeout
