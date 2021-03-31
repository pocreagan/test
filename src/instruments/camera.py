from simple_pyspin import Camera as Spinnaker

from src.base.actor import proxy
from src.base.actor import configuration
from src.instruments.base.instrument import Instrument
from src.instruments.base.instrument import instrument_debug
from src.instruments.base.instrument import InstrumentError

__all__ = [
    'Camera',
    'CameraError',
]


class CameraError(InstrumentError):
    pass


# @command_line
@instrument_debug
class Camera(Instrument):
    # ? https://pypi.org/project/simple-pyspin/

    _config = configuration.from_yml(r'W:\Test Data Backup\instruments\config\camera.yml')
    display_name = _config.field(str)
    EXPOSURE_TIME_US = _config.field(float)
    TX_WAIT_S = 0.

    def _instrument_cleanup(self) -> None:
        self.interface.close()

    def _instrument_setup(self) -> None:
        # TODO: gain settings? AOI settings? neither are used in labview version
        self.interface = Spinnaker()
        self.interface.init()
        self.interface.PixelFormat = 'RGB8'
        self.interface.ExposureAuto = 'Off'
        self.interface.ExposureMode = 'Timed'
        self.interface.ExposureTime = self.EXPOSURE_TIME_US

    @proxy.exposed
    def capture(self):
        """
        takes 212ms including start and stop
        this camera model is specced as 7.5FPS
        """
        self.interface.start()
        img = self.interface.get_array()
        self.interface.stop()
        return img

    def _instrument_check(self) -> None:
        _ = self.interface.initialized

    def _instrument_debug(self) -> None:
        from cv2 import cv2
        cv2.imshow('debug image', self.capture())
        cv2.waitKey(0)
