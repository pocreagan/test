# from collections import defaultdict
# from os import makedirs
# from pathlib import Path
# from queue import Empty
# from shutil import copyfile
# from threading import Event
# from typing import Callable
# from typing import Optional
# from typing import cast
#
# from src.base.concurrency import SYNC_COMM_ERROR_T
# from src.base.concurrency import Thread
# from src.base.log import logger
# from src.base.message import ViewAction
# from src.controller.rs485.base.constants import CFG_T
# from src.controller.rs485.base.constants import CHROMA_STARTUP_S
# from src.controller.rs485.base.constants import DATA_BITS
# from src.controller.rs485.base.constants import DTA_T
# from src.controller.rs485.base.constants import FP_T
# from src.controller.rs485.base.constants import PARITY
# from src.controller.rs485.base.constants import STOP_BITS
# from src.controller.rs485.base.constants import BadResponseError
# from src.controller.rs485.base.constants import DiscoveryError
# from src.controller.rs485.base.constants import NoFTDICableError
# from src.controller.rs485.base.constants import NoResponseError
# from src.controller.rs485.base.constants import NotConnectedError
# from src.controller.rs485.base.constants import PacketCharacteristics
# from src.controller.rs485.base.constants import Settings
# from src.controller.rs485.base.constants import Timeouts
# from src.controller.rs485.base.constants import WordCharacteristics
# from src.controller.rs485.base.error import StoppedByParent
# from src.controller.rs485.drivers.ftdi import FTDI
# from src.controller.rs485.protocols.dmx import DMX
# from src.controller.rs485.protocols.wet import NewWETCommand
# from src.controller.rs485.protocols.wet import OldWETCommand
# from src.controller.rs485.reader import ConfigReader
# from src.controller.rs485.reader import DTAReader
# from src.model.resources import APP
# from src.model.types_ import CABLE_ERROR_T
# from src.model.types_ import RESPONSE_ERROR_T
# from src.model.types_ import SN_T
# from src.model.types_ import SNS_T
# from src.model.types_ import UNITS_T
# from src.model.types_ import File
# from src.model.types_ import Orphan
# from src.model.types_ import Target
# from src.model.types_ import Unit
#
# __all__ = [
#     'FTDIFSM',
# ]
#
# log = logger(__name__)
#
#
# def _log_error(s: str) -> None:
#     log.warning(s, exc_info=True)
#
#
# BOOTLOADER_ORPHAN_CHECK_PERIOD = 4
#
#
# class Action:
#     @property
#     def units(self) -> UNITS_T:
#         return self.parent.units
#
#     @units.setter
#     def units(self, units: UNITS_T) -> None:
#         self.parent.units = units
#
#     def __post_init__(self) -> None:
#         pass
#
#     def __init__(self, parent: 'FTDIFSM') -> None:
#         self.parent = parent
#         self.ftdi = self.parent.ftdi
#         self.wet = self.parent.wet
#         self.old_wet = self.parent.old_wet
#         self.dmx = self.parent.dmx
#         self.view = self.parent.view
#         self.check_stop_e = self.parent.check_stop_e
#         try:
#             self.files = self.parent.files
#         except AttributeError:
#             pass
#         self.units_to_do: UNITS_T = list()
#         self._broadcast: bool = False
#         self.__post_init__()
#
#     def _wait_reset(self, perform_reset: bool = False) -> None:
#         if perform_reset:
#             self.wet.send_reset()
#         self.ftdi.timer.chroma_startup()
#
#     def _set_action_sns(self, target: Target) -> None:
#         self.units_to_do = [u for u in self.units if u.sn in target.sns]
#         self._broadcast = target.broadcast_write
#
#     def __call__(self, *args) -> None:
#         raise NotImplementedError
#
#
# class View:
#     def __init__(self, parent: 'FTDIFSM') -> None:
#         self.parent = parent
#         self.perform_view_action = self.parent.perform_view_action
#         self._activity = ''
#         self._last_orphan = None
#
#     def __call__(self, o: Optional[str], method: str, *args, **kwargs) -> None:
#         self.perform_view_action(o, method, *args, **kwargs)
#
#     def ftdi_cable_state(self, is_present: bool) -> None:
#         self(None, 'ftdi_cable', is_present)
#
#     def finish_action(self) -> None:
#         self(None, 'finish_action')
#
#     def status(self, s: str) -> None:
#         if self._activity != s:
#             self('activity', 'set', s)
#             self._activity = s
#
#     def orphan(self, result: Orphan) -> None:
#         if self._last_orphan is None or self._last_orphan != result:
#             self('orphans', 'orphan', result)
#             self._last_orphan == result
#
#     def update(self, unit: Unit) -> None:
#         self('manifest', 'update_unit', unit)
#
#     def new_file(self, counterpart: str, file: File) -> None:
#         self(counterpart, 'new_file', file)
#
#     def set_options(self, counterpart: str, files: list[File]) -> None:
#         self('configurationbase', 'set_options', counterpart, files)
#
#
# class IncrementalAction(Action):
#     view_action: Callable[..., None]
#     _counterpart_name = 'configurationbase'
#
#     def __init__(self, parent: 'FTDIFSM') -> None:
#         super().__init__(parent)
#         self._current_state = ''
#
#     def start(self, num_steps: int, s: str) -> None:
#         self._current_state = s
#         self.view(self._counterpart_name, 'start', num_steps, s)
#
#     def increment(self) -> None:
#         self.check_stop_e(self._current_state)
#         self.view(self._counterpart_name, 'increment')
#
#     def failure(self, s: str) -> None:
#         self.view(self._counterpart_name, 'failure', s)
#
#     def success(self) -> None:
#         self.view(self._counterpart_name, 'success')
#
#     def __call__(self, *args) -> None:
#         raise NotImplementedError
#
#     def wait_for_reset(self) -> None:
#         display_interval = .1
#         num_sleeps =int(CHROMA_STARTUP_S / display_interval)
#         self.start(num_sleeps, 'resetting')
#         for _ in range(num_sleeps):
#             self.check_stop_e('config_reset')
#             self.ftdi.delay_for(display_interval)
#             self.increment()
#
#
# class Firmware(IncrementalAction):
#     parent: 'FTDIFSM'
#
#     def _read_firmware(self, fp: FP_T) -> Optional[DTA_T]:
#         self.start(1, 'reading dta')
#         if data := cast(DTA_T, DTAReader.read(fp)):
#             self.increment()
#             return data
#         return self.failure('failed to read dta file')
#
#     def _erase_firmware(self) -> None:
#         self.start(5 if self._broadcast else 2, 'erasing firmware')
#
#         if self._broadcast:
#             self.wet.broadcast()
#             self.old_wet.broadcast()
#             self.increment()
#             self.dmx.erase()
#             with self.ftdi.baud(57600):
#                 self.increment()
#                 self.old_wet.send_erase()
#             self.old_wet.send_erase()
#
#         else:
#             _sn = self.units_to_do[0].sn
#             self.wet.address = _sn
#
#         for f in (self.wet.send_erase, self._wait_reset):
#             self.increment()
#             f()
#
#     def write(self, dta: list[bytes]) -> None:
#         self.start(len(cast(list, dta)), 'programming firmware')
#         [unit.meta.clear('fw') for unit in self.units_to_do]
#         with self.ftdi.baud(9600):
#             for chunk in dta:
#                 self.increment()
#                 self.ftdi.send(chunk)
#         self._wait_reset()
#
#     def confirm(self, version: int) -> None:
#         if len(self.units_to_do):
#             self.start(len(self.units_to_do), 'confirming firmware')
#             for unit in self.units_to_do:
#                 self.increment()
#                 self.wet.address = unit.sn
#
#                 for _ in range(self.parent.CONFIRM_RETRIES):
#                     try:
#                         assert self.wet.fw() == version
#
#                     except (AssertionError, *RESPONSE_ERROR_T):
#                         continue
#
#                     else:
#                         unit.meta.fw = version
#                         break
#
#                 else:
#                     return self.failure(f'failed to confirm {unit.sn}')
#
#         self.success()
#
#     def __call__(self, target: Target, param) -> None:
#         self.view.status('programming')
#         if data := self._read_firmware(param):
#             dta, version = data
#             self._set_action_sns(target)
#             self._erase_firmware()
#             self.wait_for_reset()
#             self.write(dta)
#             # self.confirm(version)
#             self.success()
#
#
# class Config(IncrementalAction):
#     parent: 'FTDIFSM'
#
#     def _read_config(self, fp: FP_T) -> Optional[tuple[CFG_T, CFG_T]]:
#         self.start(1, 'reading config')
#         if cfg := cast(tuple[CFG_T, CFG_T], ConfigReader.read(fp)):
#             self.increment()
#             return cfg
#         return self.failure('failed to read config file')
#
#     def _write(self, cfg: CFG_T) -> None:
#         for (target, index), payload in cfg.items():
#             self.increment()
#             self.wet.write_eeprom(target, index, payload)
#
#     def write(self, cfg: CFG_T) -> None:
#         if self._broadcast:
#             self.wet.broadcast()
#             self.start(len(cfg), 'writing config [BROADCAST]')
#             self._write(cfg)
#
#         else:
#             self.wet.address = _sn = self.units_to_do[0].sn
#             self.start(len(cfg), f'writing config [{_sn}]')
#             self._write(cfg)
#
#     def confirm(self, cfg: CFG_T) -> None:
#         for unit in self.units_to_do:
#
#             self.start(len(cfg), f'confirming {unit.sn}')
#             self.wet.address = unit.sn
#
#             for (target, index), payload in cfg.items():
#
#                 self.increment()
#                 for _ in range(self.parent.CONFIRM_RETRIES):
#                     try:
#                         assert self.wet.confirm_eeprom(target, index, payload)
#
#                     except (AssertionError, *RESPONSE_ERROR_T):
#                         pass
#
#                     else:
#                         log.info(f'confirmed sn{unit.sn}: {target} {index} {payload}')
#                         break
#
#                 else:
#                     _log_error(f'failed to confirm {unit.sn}')
#                     return self.failure(f'failed to confirm {unit.sn}')
#
#         self.success()
#
#     def __call__(self, target: Target, param) -> None:
#         self.view.status('configuring')
#         if cfg := self._read_config(param):
#             write_config, read_config = cfg
#             self._set_action_sns(target)
#             self.write(write_config)
#             self.wet.send_reset(False)
#             self.wait_for_reset()
#             self.confirm(read_config)
#
#
# class DMXChange(Action):
#     parent: 'FTDIFSM'
#
#     def __post_init__(self) -> None:
#         self.last_dmx = 1
#
#     def confirm(self, dmx: int) -> None:
#         for unit in self.units_to_do:
#             self.check_stop_e('confirming dmx')
#             self.wet.address = unit.sn
#             try:
#                 assert self.wet.dmx() == dmx
#                 self.last_dmx = unit.meta.dmx = dmx
#
#             except (AssertionError, *RESPONSE_ERROR_T):
#                 pass
#
#             self.view.update(unit)
#
#     def write(self, dmx: int) -> None:
#         [unit.meta.clear('dmx') for unit in self.units_to_do]
#         if self._broadcast:
#             self.wet.broadcast()
#         else:
#             self.wet.address = self.units_to_do[0].sn
#         self.check_stop_e('writing dmx')
#         self.wet.dmx(dmx)
#
#     def __call__(self, target: Target, dmx: int) -> None:
#         self.view.status('setting DMX')
#         self._set_action_sns(target)
#         self.write(dmx)
#         self.confirm(dmx)
#
#
# class Files(Action):
#     _persist_dir = Path(r'C:\WETBrightConfig')
#     _dirs = {
#         'dta': ({'.dta', }, 'firmware'),
#         'cfg': ({'.csv', '.xlsx'}, 'configuration'),
#     }
#
#     def add_file(self, fp: str) -> None:
#         src = Path(fp)
#         for ext, (exts, counterpart) in self._dirs.items():
#             if src.suffix in exts:
#                 dest = self._persist_dir / ext / src.name
#                 copyfile(src, dest)
#                 return self.view.new_file(counterpart, File(dest))
#
#     def copy_absent(self) -> None:
#         for ext, (exts, _) in self._dirs.items():
#             dest = self._persist_dir / ext
#             makedirs(dest, exist_ok=True)
#             for src in getattr(APP.R, ext)('').iterdir():
#                 if src.suffix in exts:
#                     _dest = dest / src.name
#                     if not _dest.exists():
#                         copyfile(src, _dest)
#
#     def get_files(self) -> None:
#         for ext, (exts, counterpart) in self._dirs.items():
#             src = (self._persist_dir / ext).iterdir()
#             _files = [File(f) for f in src if f.suffix in exts]
#             if _files != self._files[ext]:
#                 self.view.set_options(counterpart, _files)
#                 self._files[ext] = _files
#
#     def __post_init__(self) -> None:
#         self._files: dict[str, list[File]] = defaultdict(list)
#
#         try:
#             self.copy_absent()
#
#         except Exception:
#             _log_error('failed in file actor')
#
#     def __call__(self, new_fp: str = None) -> None:
#         try:
#             if new_fp is None:
#                 self.get_files()
#             else:
#                 self.add_file(new_fp)
#
#         except Exception:
#             _log_error('failed in file actor')
#
#
# class Discovery(Action):
#     DISCOVERY_TX_RETRIES = 3
#     DISCOVERY_MAX_ITERATIONS = 3
#
#     def __post_init__(self) -> None:
#         super().__post_init__()
#         self.discovery_empties = defaultdict(set)
#         self._working_empties = defaultdict(set)
#
#     def discovery_start(self) -> None:
#         self.discovery_empties.clear()
#
#     def discover_one(self) -> Optional[int]:
#         if self.wet.discovery(2 ** 23, (2 ** 24) - 1):
#             self._working_empties.clear()
#             bottom = 2 ** 23
#             for exp in range(22, -1, -1):
#
#                 top = bottom + (2 ** exp)
#
#                 if (bottom in self.discovery_empties[exp]) or (bottom in self._working_empties[exp]):
#                     bottom = top
#                     s = 'SKIPPED'
#                 else:
#
#                     self.check_stop_e('discovery')
#
#                     if self.wet.discovery(bottom, top):
#                         s = 'PRESENT'
#                     else:
#                         self._working_empties[exp].add(bottom)
#                         bottom = top
#                         s = 'NOT PRESENT'
#
#                 log.debug(f'{bottom:08d}-{top:08d} -> {s}')
#
#             bottom += 1
#             if self.wet.discovery(bottom, bottom):
#                 return bottom
#
#     def confirm_one(self, sn: int):
#         log.debug(f'confirming SN {sn}...')
#         try:
#             self.check_stop_e('discovery')
#             assert self.wet.discovery(sn, sn), 'discovering SN'
#
#             self.wet.address = sn
#
#             self.check_stop_e('discovery')
#             assert self.wet.sn() == sn, 'verifying configured SN'
#
#             self.check_stop_e('discovery')
#             self.read_metadata(self._get_unit_object(sn))
#
#             self.wet.mute()
#             assert not self.wet.discovery(sn, sn), 'verifying muted'
#
#         except (AssertionError, *RESPONSE_ERROR_T, DiscoveryError):
#             log.warning('FAILED TO CONFIRM SN %08d' % sn, exc_info=True)
#             return False
#
#         else:
#             for exp, value in self._working_empties.items():
#                 self.discovery_empties[exp] |= value
#             log.info('DISCOVERED SN %08d' % sn)
#             return True
#
#     def read_metadata(self, unit: Unit) -> None:
#         if unit.fresh:
#             for attr in unit.meta.todo:
#                 self.wet.address = unit.sn
#                 try:
#                     setattr(unit.meta, attr, getattr(self.wet, attr)())
#
#                 except RESPONSE_ERROR_T:
#                     _log_error('metadata read failure')
#
#     def confirm_discovery(self, unit: Unit) -> None:
#         unit.confirmed = self.confirm_one(unit.sn)
#         unit.end_discovery()
#         self.view.update(unit)
#         if unit.expired:
#             self.units = [unit for unit in self.units if not unit.expired]
#
#     def _get_unit_object(self, sn: SN_T) -> Unit:
#         for unit in self.units:
#             if unit.sn == sn:
#                 return unit
#         unit = Unit(sn)
#         self.units.append(unit)
#         return unit
#
#     def confirm_known(self) -> None:
#         self.view.status('ready')
#         [self.confirm_discovery(unit) for unit in self.units]
#
#     def discovery(self) -> None:
#         i = 0
#         self.discovery_start()
#         for _ in range(self.DISCOVERY_MAX_ITERATIONS):
#             if self.wet.discovery_on_full_range():
#                 if sn := self.discover_one():
#                     self.view.status('discovery')
#                     self.confirm_discovery(self._get_unit_object(sn))
#             else:
#                 i += 1
#                 if i > self.DISCOVERY_TX_RETRIES:
#                     break
#                 log.debug(f'no SNs discovered on full range {i}x')
#
#     def __call__(self) -> None:
#         self.confirm_known()
#         try:
#             self.discovery()
#         except DiscoveryError:
#             pass
#
#
# class OrphanCheck(Action):
#     def __post_init__(self) -> None:
#         self.do_bootloader = 0
#         self._result = Orphan(False, False, False)
#
#     def _one_check(self, k: str, is_present: bool) -> None:
#         self.check_stop_e(k)
#         setattr(self._result, k, is_present)
#
#     def _update_counter(self) -> None:
#         self.do_bootloader += 1
#         self.do_bootloader %= BOOTLOADER_ORPHAN_CHECK_PERIOD
#
#     def __call__(self) -> None:
#
#         self.wet.broadcast()
#         self.old_wet.broadcast()
#
#         self._one_check('no_discovery', self.wet.discovery_on_full_range() or self.wet.sn_query_any_response())
#         self._one_check('old_firmware', self.old_wet.sn_query_any_response())
#
#         if self._result.bootloader or not self.do_bootloader:
#             self._one_check('bootloader', self.dmx.boot_reset())
#
#         self._update_counter()
#         self.view.orphan(self._result)
#
#
#
# class Stable(Action):
#     def __post_init__(self) -> None:
#         self.discovery = Discovery(self.parent)
#         self.orphan_check = OrphanCheck(self.parent)
#
#     def __call__(self) -> None:
#         try:
#             # self.read_metadata()
#             self.discovery()
#             self.orphan_check()
#
#         except StoppedByParent:
#             self.orphan_check.do_bootloader = 0
#             raise
#
#
# class Command(Action):
#     def __post_init__(self) -> None:
#         self.dmx_change = DMXChange(self.parent)
#         self.firmware = Firmware(self.parent)
#         self.config = Config(self.parent)
#
#     def perform_command(self, f, *args, **kwargs) -> None:
#         try:
#             action = getattr(self, f)
#             assert callable(action)
#             action(*args, **kwargs)
#
#         except (AttributeError, AssertionError):
#             _log_error(f'{f} not a valid command')
#
#         except TypeError:
#             _log_error(f'{f} does not take args {args} {kwargs}')
#
#         finally:
#             self.view.finish_action()
#
#     def __call__(self, poll: bool = False) -> None:
#         try:
#             f, args, kwargs = self.parent._q.get(timeout=(0. if poll else .1))  # type: ignore
#
#         except Empty:
#             if not poll:
#                 _log_error('dequeue error in FTDI FSM')
#
#         except ValueError:
#             _log_error('dequeue error in FTDI FSM')
#
#         else:
#             self.perform_command(f, *args, **kwargs)
#
#
# class FTDIFSM(Thread):
#     CONFIRM_RETRIES = 4
#
#     def ftdi_cable_state(self, is_present: bool) -> None:
#         if self._cable_present is None or self._cable_present ^ is_present:
#             self.view.ftdi_cable_state(is_present)
#             self._cable_present = is_present
#
#     def __post_init__(self) -> None:
#         self.units: UNITS_T = list()
#         self._cable_present: Optional[bool] = None
#         self._ftdi_settings = Settings(
#             250000, Timeouts(20, 10),
#             WordCharacteristics(DATA_BITS.EIGHT, STOP_BITS.TWO, PARITY.NONE),
#             PacketCharacteristics(5, 5, .01)
#         )
#
#         self.ftdi = FTDI()
#         self.dmx = DMX(self.ftdi)
#         self.wet = NewWETCommand(self.ftdi)
#         self.old_wet = OldWETCommand(self.ftdi)
#
#         self.view = View(self)
#         self.files = Files(self)
#
#         self.stable = Stable(self)
#         self.command = Command(self)
#
#         Thread.__post_init__(self)
#         self.files()
#
#     def release(self, *, fail_silently: bool = False, clear_input: bool=True) -> None:
#         try:
#             self.wet.broadcast()
#             self.old_wet.broadcast()
#             self.ftdi.break_condition = False
#             self.wet.unmute()
#             if clear_input:
#                 self.ftdi.clear_read_buffer()
#             if not self.units:
#                 self.wet.send_reset()
#
#         except Exception:
#             if not fail_silently:
#                 raise
#
#     def check_stop_e(self, s: str) -> None:
#         if self.e.is_set():
#             self.e.clear()
#             raise StoppedByParent(f'stopped in {s}')
#
#     def open_port(self) -> None:
#         self.ftdi.open(self._ftdi_settings)
#         self.ftdi_cable_state(True)
#
#     def port_closed(self) -> None:
#         self.units.clear()
#         self.ftdi_cable_state(False)
#
#     def poll(self) -> None:
#         try:
#             self.open_port()
#
#             while 1:
#                 self.files()
#                 self.release()
#                 self.stable()
#                 self.command(poll=True)
#
#         except StoppedByParent:
#             self.release()
#             self.command()
#
#         except CABLE_ERROR_T:
#             self.port_closed()
#
#         except (KeyboardInterrupt, *SYNC_COMM_ERROR_T):
#             log.error('stopped', exc_info=True)
#             raise
#
#         except Exception:
#             _log_error('unhandled exception in FTDI FSM')
#
#     def on_shutdown(self):
#         self.units.clear()
#         self.release(fail_silently=True, clear_input=False)
#         self.ftdi.close()
#
#     def __init__(self, view_q, **kwargs) -> None:
#         self.e = Event()
#         self.view_q = view_q
#         self._name = type(self).__name__
#         super().__init__(**kwargs)
#
#     def perform_view_action(self, o, f: str, *args, **kwargs):
#         msg = ViewAction((self._name if o is self else o), f, *args, **kwargs)
#         log.info(str(msg))
#         self.view_q.put(msg)
