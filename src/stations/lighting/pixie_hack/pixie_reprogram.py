import time

from progressbar import progressbar

from src.base.log import logger
from src.controller.lighting.pixie_hack import HackScript
from src.pixie_hack.messages import FirmwareIncrement
from src.pixie_hack.messages import FirmwareSetup

log = logger(__name__)


# noinspection PyPep8Naming
class Programming(HackScript):
    firmware_path = r'W:\Test Data Backup\test\fw\Pixie_Autocycle_RGBW+RGBW+Full_v0_6.dta'

    def FirmwareIncrement(self, msg: FirmwareIncrement) -> None:
        self.progress.update(msg.i + 1)

    def FirmwareSetup(self, msg: FirmwareSetup) -> None:
        print('\nprogramming firmware...\n')
        self.progress = progressbar.ProgressBar(maxval=msg.n)
        self.progress.start()

    def handler(self, msg) -> None:
        return getattr(self, type(msg).__name__)(msg)

    def __call__(self) -> None:
        self.ftdi.dta_program_firmware(self.firmware_path, self.handler)
        print('\n\nprogramming complete.\n')
        time.sleep(2.)


if __name__ == '__main__':
    Programming.run()
