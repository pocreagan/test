import subprocess
from subprocess import CalledProcessError
from time import sleep
from typing import List
from typing import Type

from base.decorators import classproperty
from controller.rs485.base.constants import DATA_BITS
from controller.rs485.base.constants import PacketCharacteristics
from controller.rs485.base.constants import PARITY
from controller.rs485.base.constants import Settings
from controller.rs485.base.constants import STOP_BITS
from controller.rs485.base.constants import Timeouts
from controller.rs485.base.constants import WordCharacteristics
from controller.rs485.protocols.dmx import DMX
from src.controller.rs485.drivers.ftdi import FTDI
from src.base.log import logger


class XMCFlasherError(Exception):
    pass


class BreakWhenShouldNotError(Exception):
    pass


class BMISetError(XMCFlasherError):
    pass


class BootLoaderLoadError(XMCFlasherError):
    pass


class Bootloader:
    XMC_FLASHER = r"\\wet-pdm\Common\Test Data Backup\instruments\drivers\XMCFlasher.jar"
    BOOT_ERASE_FP = r'\\wet-pdm\Common\Test Data Backup\instruments\fw\BMI_Unlock.dta'

    _ARGS = ['java', '-jar', XMC_FLASHER, '-device']  # + micro mn, ex: XMC1302-0128
    BMI_ARGS = ['-setBMI', 'UM_DEBUG_SPD1']
    BOOT_ARGS = ['-erase', '-program']  # + bootloader fp

    WAIT_AFTER_BOOT_ERASE_S = .2

    @classproperty.cached
    def boot_erase_dta(self) -> List[bytes]:
        with open(self.BOOT_ERASE_FP, 'rb') as f:
            data = list(map(int, f.read()))
        return [bytes(data[i:i + 271]) for i in range(0, len(data), 271)]

    def __init__(self) -> None:
        self.ftdi = FTDI(
            Settings(
                250000, Timeouts(20, 10),
                WordCharacteristics(DATA_BITS.EIGHT, STOP_BITS.TWO, PARITY.NONE),
                PacketCharacteristics(5, 5, .01)
            )
        )
        self.dmx = DMX(self.ftdi)

    def check_for_line_in_break_state(self) -> None:
        if self.ftdi.detect_break():
            raise BreakWhenShouldNotError

    def erase_bootloader(self) -> bool:
        self.ftdi.clear_read_buffer()
        self.check_for_line_in_break_state()
        if self.dmx.boot_reset():
            with self.ftdi.baud(9600):
                [self.ftdi.send(chunk) for chunk in self.boot_erase_dta]
        sleep(self.WAIT_AFTER_BOOT_ERASE_S)
        return not self.dmx.boot_reset()

    @staticmethod
    def run_command(command_args: List[str], exception: Type[XMCFlasherError]) -> None:
        try:
            result = subprocess.run(command_args, text=True, capture_output=True)
            return_code = result.returncode
            if return_code:
                cmd = ' '.join(command_args)
                raise XMCFlasherError(f'cmd="{cmd}", stderr="{result.stderr}", r={return_code}')
        except (CalledProcessError, XMCFlasherError) as e:
            raise exception from e

    def bmi(self, micro_mn: str) -> None:
        self.run_command(self._ARGS + [micro_mn] + self.BMI_ARGS, BMISetError)

    def bootloader(self, micro_mn: str, fp: str) -> None:
        self.run_command(self._ARGS + [micro_mn] + self.BOOT_ARGS + [fp], BootLoaderLoadError)

    def __call__(self) -> None:
        micro_mn = 'XMC1302-0128'
        self.bmi(micro_mn)
        self.bootloader(
            micro_mn,
            r"\\wet-pdm\Common\Test Data Backup\instruments\fw\80-01002_Bootloader_Chroma_Controller.hex"
        )

import subprocess
from subprocess import CalledProcessError
from time import sleep
from typing import List
from typing import Type
def test_sigkill():
    proc = subprocess.Popen(['ping', '-n', '3', '127.0.0.1'])
    print(proc.communicate())

if __name__ == '__main__':
    with logger:
        # bootloader = Bootloader()
        # bootloader.erase_bootloader()
        # bootloader()
        test_sigkill()
