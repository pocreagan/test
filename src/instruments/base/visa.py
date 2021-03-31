from time import time

import pyvisa

from src.instruments.base.instrument import Instrument
from src.instruments.base.instrument import InstrumentError

__all__ = [
    'VISA',
]


class VISA(Instrument):
    def _instrument_check(self) -> None:
        raise NotImplementedError

    def _instrument_debug(self) -> None:
        raise NotImplementedError

    PATTERN = r'?*::INSTR'
    TX_WAIT_S = 0.

    def _instrument_setup(self):
        rm = pyvisa.ResourceManager()
        ports = rm.list_resources(self.PATTERN)
        if len(ports) != 1:
            raise InstrumentError(
                f'could not select one instrument from ports {ports} with pattern `{self.PATTERN}`'
            )
        self.interface = rm.open_resource(ports[0])
        self.interface.open()

    def _instrument_cleanup(self) -> None:
        self.interface.close()

    def read(self, packet: str):
        self.proxy_check_cancelled()
        # noinspection PyUnresolvedReferences
        rx = self.interface.query_ascii_values(packet, converter='f')  # type: ignore
        if len(rx) == 1:
            rx = rx[0]
        self.debug(f'receive -> "{rx}"')
        return rx

    def write(self, packet: str) -> None:
        self._instrument_delay(self._next_tx - time())
        # noinspection PyUnresolvedReferences
        self.interface.write_ascii_values(packet, [])  # type: ignore
        self.set_next_tx_time()
        self.debug(f'transmit -> "{packet}"')
