import collections
import re
from enum import Enum
from math import floor
from time import time
from typing import cast
from typing import Dict
from typing import List
from typing import Optional
from typing import Type
from typing import Union

import nidaqmx
import nidaqmx.constants
import nidaqmx.stream_readers
import nidaqmx.system
import nidaqmx.system.system
# SUPPRESS-LINTER <pycharm bug>
# noinspection PyPackageRequirements
import numpy as np
from nidaqmx.constants import CurrentUnits
from nidaqmx.constants import VoltageUnits
from nidaqmx.system.storage.persisted_scale import PersistedScale
from typing_extensions import Final

from src.base import register
from base.concurrency import proxy
from src.base.decorators import check_for_required_attrs
from src.base.general import setdefault_attr_from_factory
from src.base.log import logger
# SUPPRESS-LINTER <want to keep these concerns separate>
# noinspection PyProtectedMember
from src.instruments.base.instrument import Instrument
from src.instruments.base.instrument import InstrumentError

__all__ = [
    'DAQTaskError',
    'DAQChassis',
    'DAQModule',
    'DAQTask',
    'DITask',
    'DOTask',
    'DIChannel',
    'DOChannel',
    'AIContinuous',
    'AIFinite',
    'AIVoltageChannel',
    'AICurrentChannel',
]

log = logger(__name__)


class DAQTaskError(InstrumentError):
    pass


_chassis_sn_key = '_chassis_sn_key_'


class DAQChassis:
    _dev_d: collections.defaultdict

    def __make_device_d(self) -> None:
        self.__class__._dev_d = _daq_devices_d = collections.defaultdict(dict)
        for _chassis in nidaqmx.system.system.System().devices:
            for _module in _chassis.chassis_module_devices:
                _mn = int(re.findall(r'^NI (\d{4})', _module.product_type)[0])
                _slot = _module.compact_daq_slot_num - 1
                _daq_devices_d[_chassis.dev_serial_num][(_slot, _mn)] = _module

    def __init__(self, sn: int) -> None:
        self._name_set = False
        self.modules_assigned = set()
        if not hasattr(self.__class__, '_dev_d'):
            self.__make_device_d()
        if sn not in self.__class__._dev_d:
            raise ValueError(f'daq chassis sn={sn} not found')
        self.sn = sn

    def __set_name__(self, owner, name):
        if hasattr(owner, _chassis_sn_key):
            raise ValueError('one daq task cannot span multiple chassis')
        setattr(owner, _chassis_sn_key, self.sn)
        self._name_set = True

    def module(self, slot: int, mn: int) -> 'DAQModule':
        # if not self._name_set:
        #     raise ValueError('chassis must be assigned as a task class attr')
        k = (slot, mn)
        s = f'daq module <slot={slot}, mn={mn}>'
        if k in self.modules_assigned:
            raise ValueError(f'cannot assign {s} more than once')
        try:
            module = self.__class__._dev_d[self.sn][k]
        except KeyError:
            raise ValueError(f'{s} not found in chassis <sn={self.sn}>')
        self.modules_assigned.add(k)
        return DAQModule(module)


class DAQModule:
    def __init__(self, module: nidaqmx.system.Device) -> None:
        self.module = module
        self.device_name = module.name

    def __set_name__(self, owner, name):
        setdefault_attr_from_factory(owner, _module_map_key, dict)[self.device_name] = self

    def __get__(self, instance, owner):
        self.task_instance = instance
        self.task_class = owner
        return self

    def self_check(self) -> bool:
        try:
            self.module.self_test_device()
            return True
        except nidaqmx.DaqError:
            log.error(f'self-check failed for {self}', stack_info=True)
            return False

    def __repr__(self) -> str:
        return f'{type(self).__name__}(device_name={self.device_name})'


class ScaleBase:

    @classmethod
    def name(cls) -> str:
        if not getattr(cls, '_name', None):
            setattr(cls, '_name', '__'.join([cla.__qualname__ for cla in cls.__mro__[:-1]]).replace('.', '_'))
        return getattr(cls, '_name')

    @classmethod
    def make(cls, scale_type) -> Dict[str, Union[int, str]]:
        assert Scale.From.supports(scale_type), f'value {scale_type} not supported for scaling.'
        if cls._should_make():
            if not hasattr(cls, 'made_scales'):
                cls.made_scales = set()
            if not cls.name() in cls.made_scales:
                try:
                    PersistedScale(cls.name()).delete()
                except nidaqmx.DaqError:
                    pass
                cls._make()
                cls.made_scales.add(cls.name())
            return dict(units=scale_type, custom_scale_name=cls.name())
        return {}

    @classmethod
    def _should_make(cls) -> bool:
        """
        return bool(settings != defaults)
        """
        raise NotImplementedError

    @classmethod
    def _make(cls) -> None:
        """
        scale-specific nidaqmx.Scale method
        """
        raise NotImplementedError


class Scale:
    class From:
        VOLTAGE = VoltageUnits.FROM_CUSTOM_SCALE
        CURRENT = CurrentUnits.FROM_CUSTOM_SCALE

        @classmethod
        def supports(cls, value) -> bool:
            if isinstance(value, Enum):
                return value in cls.__dict__.values()
            return False

    class Linear(ScaleBase):
        m: float = 1.
        y: float = 0.

        @classmethod
        def _should_make(cls):
            return cls.m != 1. or cls.y != 0.

        @classmethod
        def _make(cls):
            nidaqmx.Scale.create_lin_scale(cls.name(), cls.m, cls.y)

    Type = Union[
        Type[Linear],
    ]


_channel_map_key = '_channel_map_key_'
_identifier_set_key = '_identifier_set_key_'
_module_map_key = '_module_map_key'


class Channel(register.Mixin):
    channel_name: str  # ex: '{device_name}/ai{_ch}'
    channel_type: str  # ex: 'ai_channels' <- channel collection object attr k
    # noinspection SpellCheckingInspection
    channel_method: str  # ex: 'add_ai_voltage_chan' <- method to call on collection

    def add_to_task(self) -> None:
        method = getattr(getattr(self.task_instance.task, self.channel_type), self.channel_method)
        method(self.identifier, **getattr(self, 'scale_kwargs', {}))
        self.task_instance.debug(f'{self} added to task')

    @check_for_required_attrs.declared_on_class(channel_type=str, channel_name=str, channel_method=str)
    def __init__(self, module: DAQModule, ch: int):
        self.module = module
        self.device_name = module.device_name
        self.daq_channel_number = ch

    def __set_name__(self, task_class: Type['DAQTask'], name: str) -> None:
        self.task_class = task_class
        self.name = name
        self.identifier = self.channel_name.format(**self.__dict__)

        identifier_set = setdefault_attr_from_factory(self.task_class, _identifier_set_key, set)
        if self.identifier in identifier_set:
            raise ValueError(f'channel {self.identifier} redeclared.')
        identifier_set.add(self.identifier)

        channel_map = setdefault_attr_from_factory(self.task_class, _channel_map_key, dict)
        self.task_ch_id = 0 if not channel_map else max(channel_map.keys()) + 1
        channel_map[self.task_ch_id] = self

    def __get__(self, task_instance: 'DAQTask', owner: Type['DAQTask']):
        self.task_instance = task_instance
        return self

    def __repr__(self) -> str:
        return f'{type(self).__name__}({self.identifier})'


class _DChannel(Channel):
    state: bool
    channel_name: Final = '{device_name}/port{port}/line{daq_channel_number}'

    def __init__(self, module: DAQModule, port: int, ch: int):
        self.port = port
        super().__init__(module, ch)


class DIChannel(_DChannel):
    channel_type: Final = 'di_channels'
    # noinspection SpellCheckingInspection
    channel_method: Final = 'add_di_chan'


class DOChannel(_DChannel):
    channel_type: Final = 'do_channels'
    # noinspection SpellCheckingInspection
    channel_method: Final = 'add_do_chan'


class AIChannel(Channel):
    channel_type: Final = 'ai_channels'
    channel_name: Final = '{device_name}/ai{daq_channel_number}'

    scale_type: Enum
    _scale: Scale.Type

    def scale(self, scale: Scale.Type):
        if hasattr(self, '_scale'):
            raise AttributeError('Cannot apply two scales to one channel')
        self._scale = scale
        return self

    @register.after('__set_name__')
    def _make_scale(self) -> None:
        self.scale_kwargs = self._scale.make(self.scale_type) if hasattr(self, '_scale') else {}


class AIVoltageChannel(AIChannel):
    # noinspection SpellCheckingInspection
    channel_method: Final = 'add_ai_voltage_chan'
    scale_type: Final = Scale.From.VOLTAGE


class AICurrentChannel(AIChannel):
    # noinspection SpellCheckingInspection
    channel_method: Final = 'add_ai_current_chan'
    scale_type: Final = Scale.From.CURRENT


class DAQTask(Instrument):
    channels: List[Channel]
    modules: List[DAQModule]
    TX_WAIT_S = 0.

    @register.before('__init__')
    def _accumulate_pieces(self) -> None:
        cls = type(self)
        self.channels = [ch.__get__(self, cls) for ch in getattr(self, _channel_map_key).values()]
        self.num_channels = len(self.channels)
        self.modules = [module.__get__(self, cls) for module in getattr(self, _module_map_key).values()]

    @register.after('_instrument_setup')
    def _start_task(self) -> None:
        self.task.start()

    def _instrument_setup(self) -> None:
        self.task = nidaqmx.Task()
        [ch.add_to_task() for ch in self.channels]

    def _instrument_cleanup(self) -> None:
        for op in ('stop', 'close'):
            try:
                getattr(self.task, op)()
            except AttributeError:
                pass

    def _instrument_check(self) -> None:
        if not all(module.self_check() for module in self.modules):
            raise DAQTaskError('modules failed self-check')

    def _instrument_debug(self) -> None:
        raise NotImplementedError

    def __repr__(self) -> str:
        return f'{type(self).__name__}(channels={self.channels})'


class AITask(DAQTask):
    def _instrument_debug(self) -> None:
        raise NotImplementedError

    _reader: nidaqmx.stream_readers.AnalogMultiChannelReader
    acquisition_length_in_seconds: float
    _sample_mode: nidaqmx.constants.AcquisitionType
    acquisition_rate_in_hertz: Optional[float] = None
    _data: np.ndarray
    _acq_duration: float
    _next_read: float

    def _process_data(self) -> None:
        raise NotImplementedError

    def _read(self) -> None:
        """
        reads new samples from DAQ buffer into instance._data array
        behavior on read should be specified in _process_data and _on_after
        """
        self._reader.read_many_sample(self._data, number_of_samples_per_channel=self.num_samp)
        self._process_data()

    # noinspection SpellCheckingInspection
    @register.after('__init__')
    @check_for_required_attrs.declared_on_class(acquisition_length_in_seconds=(int, float),
                                                _sample_mode=nidaqmx.constants.AcquisitionType)
    def _non_task_setup(self):
        self.acquisition_length_in_seconds = float(self.acquisition_length_in_seconds)
        max_acq = float(floor(min(list(map(lambda o: getattr(
            o.module, 'ai_max_multi_chan_rate'), self.modules
                                           )))))
        if self.acquisition_rate_in_hertz is None:
            self.acquisition_rate_in_hertz = max_acq
        else:
            self.acquisition_rate_in_hertz = min(self.acquisition_rate_in_hertz, max_acq)
        self.num_samp = int(self.acquisition_length_in_seconds * self.acquisition_rate_in_hertz)
        self._acq_duration = 1 / self.num_samp
        self._next_read = time() + self._acq_duration
        self._data = np.zeros(shape=(self.num_channels, self.num_samp), dtype=np.float_)

    @register.before('_start_task')
    def _task_setup(self):
        self.task.timing.cfg_samp_clk_timing(self.acquisition_rate_in_hertz, sample_mode=self._sample_mode)
        self._reader = nidaqmx.stream_readers.AnalogMultiChannelReader(self.task.in_stream)


class AIFinite(AITask):
    def _instrument_debug(self) -> None:
        raise NotImplementedError

    _sample_mode: Final = nidaqmx.constants.AcquisitionType.FINITE

    def _process_data(self) -> None:
        raise NotImplementedError

    @proxy.exposed
    def read(self) -> np.ndarray:
        """
        exposes AnalogRead._read and returns data directly
        """
        self._instrument_delay(time() - self._next_read)
        self._read()
        self._next_read = time() + self._acq_duration
        return self._data


class AIContinuous(AITask):
    def _instrument_debug(self) -> None:
        raise NotImplementedError

    _sample_mode: Final = nidaqmx.constants.AcquisitionType.CONTINUOUS

    def _process_data(self) -> None:
        raise NotImplementedError

    def _read_callback(self, task_handle, event_type, number_of_samples, callback_data) -> int:
        # *this exact prototype must be registered to work with the nidaqmx API
        _ = task_handle, event_type, number_of_samples, callback_data
        self._read()
        return 0

    @register.after('_task_setup')
    def _read_setup(self):
        self.task.in_stream.relative_to = nidaqmx.constants.ReadRelativeTo.MOST_RECENT_SAMPLE
        self.task.in_stream.offset = -self.num_samp
        self.task.in_stream.over_write = nidaqmx.constants.OverwriteMode.OVERWRITE_UNREAD_SAMPLES
        # SUPPRESS-LINTER <nidaqmx func proto wrong>
        # noinspection PyTypeChecker
        self.task.register_every_n_samples_acquired_into_buffer_event(self.num_samp, self._read_callback)


class DOTask(DAQTask):
    """each write operation takes 2-3ms on an NI 9474"""

    def _instrument_debug(self) -> None:
        raise NotImplementedError

    channels: List[DOChannel]
    _write_list: List[bool]

    def __write(self, values: List[bool]) -> None:
        self.proxy_check_cancelled()
        if not hasattr(self, '_write_list'):
            self._write_list = values
        else:
            self._write_list[:] = values
        if self._should_be_open:
            self.task.write(values, auto_start=False)
            [setattr(ch, '_state', v) for ch, v in zip(self.channels, values)]
            self.debug(f'wrote {values}')

    @proxy.exposed
    @register.after('__init__')
    @register.before('_instrument_cleanup')
    def all_off(self):
        self.set_all([False] * self.num_channels)
        return self

    @proxy.exposed
    def all_on(self):
        self.set_all([True] * self.num_channels)
        return self

    @proxy.exposed
    def set_one(self, ch: int, state: bool) -> None:
        try:
            _ = self.channels[ch]
        except IndexError:
            raise DAQTaskError(f'ch{ch} not defined on {self}')
        values = self._write_list
        values[ch] = state
        self.__write(values)

    @proxy.exposed
    def set_all(self, values: List[bool]) -> None:
        if len(values) != self.num_channels:
            raise DAQTaskError(
                f'set_all must be called with List[bool] len={self.num_channels} values'
            )
        self.__write(values)


class DITask(DAQTask):
    """each read operation takes 2-3ms on an NI 9401"""

    def _instrument_debug(self) -> None:
        raise NotImplementedError

    @proxy.exposed
    def read(self) -> List[bool]:
        self.proxy_check_cancelled()
        return cast(List[bool], list(zip(*self.task.read(number_of_samples_per_channel=1)))[0])

    @proxy.exposed
    def read_as_int(self) -> int:
        return int(''.join(str(int(v)) for v in self.read()), 2)
