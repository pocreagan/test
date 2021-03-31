import ctypes
import logging
from ctypes import c_char_p
from ctypes import c_int16
from ctypes import c_int32
from ctypes import c_int8
from dataclasses import dataclass
from dataclasses import fields
from dataclasses import InitVar
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from typing import Callable
from typing import cast
from typing import Dict
from typing import Optional

from src.base.actor import proxy
from src.base.actor import configuration
from src.instruments.base.dll import DLLFunc
from src.instruments.base.dll import load_dll
from src.instruments.base.instrument import Instrument
from src.instruments.base.instrument import instrument_debug
from src.instruments.base.instrument import InstrumentError

__all__ = [
    'LightMeter',
    'LightMeasurement',
    'LightMeterError',
]


class LightMeterError(InstrumentError):
    pass


@dataclass
class LightMeasurement:
    """
    read_settings one chromaticy and illuminance measurement from light meter
    performs calculation necessary to add duv value
    exposes .distance_from() and .percent_drop_from(), which may be useful for p/f
    """
    x: float
    y: float
    fcd: float
    CCT: float
    du: InitVar[float]
    dv: InitVar[float]
    duv: Optional[float] = None

    def __post_init__(self, du: float, dv: float) -> None:
        self.duv = self._root_sum_squares(du, dv)

    @staticmethod
    def _root_sum_squares(a: float, b: float) -> float:
        return ((a ** 2) + (b ** 2)) ** .5

    def distance_from(self, other) -> float:
        return self._root_sum_squares(self.x - other.x, self.y - other.y)

    def percent_drop_from(self, other) -> float:
        return ((other.fcd - self.fcd) / other.fcd) * 100.

    def as_dict(self) -> Dict[str, float]:
        return {k.name: getattr(self, k.name) for k in fields(self)}


@instrument_debug
class LightMeter(Instrument):
    _config = configuration.from_yml(r"instruments\light_meter.yml")
    _DLL_FP = _config.field(str)
    display_name = _config.field(str)
    EXPOSURE_TIME = _config.field(int)
    BEFORE_INIT_S = _config.field(float)
    AFTER_INIT_S = _config.field(float)
    MAX_EXPOSURE_TIME_US = _config.field(int)
    CALIBRATION_MS = _config.field(int)
    TX_WAIT_S = 0.

    MEASUREMENT_REGISTERS = {
        'x': 1,
        'y': 2,
        'fcd': 258,
        'CCT': 259,
        'du': 33,
        'dv': 34,
    }

    _sn: bytes

    def __init__(self) -> None:
        try:
            self._dll = load_dll(Path(self._DLL_FP))
        except OSError as e:
            raise LightMeterError(f'failed to load DLL at {self._DLL_FP}') from e

        self.exposure_time = c_int16(self.EXPOSURE_TIME)
        self.max_exposure_time = c_int32(self.MAX_EXPOSURE_TIME_US)
        self.calibration_m_sec = c_int32(self.CALIBRATION_MS)
        self.registers = {k: c_int32(v) for k, v in self.MEASUREMENT_REGISTERS.items()}

        self.i = c_int32(0)
        self.ctrl = c_int32(0)
        self.mode = c_int32(0)
        self.isMonitor = c_int32(1)
        self.isAuto = c_int16(0)

        self.mk_FindFirst = DLLFunc(self._dll.mk_FindFirst, c_int8, [c_char_p])
        self.mk_Init = DLLFunc(self._dll.mk_Init, c_int8, [c_int32, c_int32],
                               args=(self.isMonitor, self.calibration_m_sec))
        self.mk_Close = DLLFunc(self._dll.mk_Close)
        self.mk_OpenSpDev = DLLFunc(self._dll.mk_OpenSpDev, c_int32, [c_char_p])
        self.mk_Capture = DLLFunc(self._dll.mk_Msr_Capture, c_int8, [c_int32, c_int16, c_int16],
                                  args=(self.i, self.isAuto))
        self.mk_GetData = DLLFunc(self._dll.mk_GetData, c_int8, [c_int32, c_int32, c_char_p],
                                  args=(self.i,))
        self.mk_AutoDarkCtrl = DLLFunc(self._dll.mk_Msr_AutoDarkCtrl, c_int8, [c_int32, c_int32],
                                       args=(self.i, self.ctrl))
        self.mk_SetExpMode = DLLFunc(self._dll.mk_Msr_SetExpMode, c_int8, [c_int32, c_int32],
                                     args=(self.i, self.mode))
        self.mk_SetMaxExpTime = DLLFunc(self._dll.mk_Msr_SetMaxExpTime, c_int8, [c_int32, c_int32],
                                        args=(self.i, self.max_exposure_time))
        self.mk_MsrDark = DLLFunc(self._dll.mk_Msr_Dark, c_int8, [c_int32], args=(self.i,))

    @proxy.exposed
    def _instrument_check(self) -> None:
        """
        determine whether light meter is communicating
        """
        self._sn = b''
        response_buffer = ctypes.create_string_buffer(b'\000' * 64)
        pointer = ctypes.c_char_p(ctypes.addressof(response_buffer))
        self.mk_FindFirst(pointer)
        self._sn = cast(bytes, response_buffer.value)
        self.mk_OpenSpDev(pointer)

    def _instrument_cleanup(self):
        self.mk_Close()

    def _wait_for_init(self, timeout: float = None) -> bool:
        """
        waits for 10ms every time .instrument_check() indicates the light meter hasn't finished connecting
        times out after @timeout or 10s if timeout is None
        returns last .instrument_check return value
        """
        tf = perf_counter() + (10. if timeout is None else timeout)
        while perf_counter() < tf:
            self._instrument_delay(.01)
            self._instrument_check()
            if self._sn != b'':
                return True
        raise LightMeterError('failed to confirm open')

    def _instrument_setup(self):
        """
        .mk_Init() really does take 300ms
        """
        try:
            self._instrument_check()
        except OSError:
            self.mk_Init()
            return self._wait_for_init(self.AFTER_INIT_S * 1.5)
        else:
            return True

    def get_data(self, register: c_int32) -> float:
        """
        grab the value in one of the light meter's registers
        this is how measurement data are retrieved
        takes < 50us
        """
        response_buffer = ctypes.c_float(9999.9999)
        pointer = ctypes.c_char_p(ctypes.addressof(response_buffer))
        self.mk_GetData(register, pointer)
        return cast(float, response_buffer.value)

    @staticmethod
    @lru_cache(maxsize=None)
    def __make_exposure_time(exposure_time: int) -> c_int16:
        return c_int16(exposure_time)

    @proxy.exposed
    def measure(self, exposure_time: int = None) -> LightMeasurement:
        """
        ::exposure_time:: is in 100us increments
        take a light measurement (CIE, CCT, fcd, du, dv)
        50ms is unreasonable
        """
        _exp_t = self.exposure_time if exposure_time is None else self.__make_exposure_time(exposure_time)
        try:
            self.proxy_check_cancelled()
            self.mk_Capture(_exp_t)
            meas = LightMeasurement(**{k: self.get_data(v) for k, v in self.registers.items()})
            self.info(meas)
            return meas
        except OSError as e:
            raise LightMeterError('failed to measure') from e

    @proxy.exposed
    def calibrate(self, consumer: Callable = None) -> None:
        """
        __perform_task dark calibration.
        should only be performed when the sensor is covered or when
        it's at the top of the light tunnel and no light is on under it
        """
        consumer = consumer if callable(consumer) else self.info
        try:
            for f in (self.mk_AutoDarkCtrl,
                      self.mk_SetExpMode,
                      self.mk_SetMaxExpTime,
                      self.mk_MsrDark):
                self.proxy_check_cancelled()
                f()
                consumer(f.__name__)
        except OSError as e:
            raise LightMeterError('failed to calibrate') from e

    def _instrument_debug(self) -> None:
        [self.measure() for _ in range(10)]
