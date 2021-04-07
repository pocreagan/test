from datetime import datetime
from operator import attrgetter
from time import sleep
from typing import List
from typing import Union

from attrdict import AttrDict

from src.base.concurrency import proxy
from src.base.general import test_nom_tol
from src.base.log import logger
from src.instruments.base.instrument import instruments_joined
from src.instruments.base.instrument import instruments_spawned
from src.instruments.dc_power_supplies import DCLevel
from src.instruments.dc_power_supplies.bk_ps import BKPowerSupply
from src.instruments.light_meter import LightMeasurement
from src.instruments.light_meter import LightMeter
from src.instruments.light_meter import LightMeterError
from src.instruments.light_meter import ThermalDropSample
from src.instruments.wet.rs485 import ConfigIncrement
from src.instruments.wet.rs485 import FirmwareIncrement
from src.instruments.wet.rs485 import MicroState
from src.instruments.wet.rs485 import RS485
from src.instruments.wet.rs485 import RS485Error
from src.instruments.wet.rs485 import WETCommandError
from src.model import configuration
from src.model.db import connect
from src.model.db.schema import Configuration
from src.model.db.schema import ConfirmUnitIdentityIteration
from src.model.db.schema import EEPROMConfigIteration
from src.model.db.schema import FirmwareIteration
from src.model.db.schema import LightingDUT
from src.model.db.schema import LightingStation3Iteration
from src.model.db.schema import LightingStation3LightMeasurement
from src.model.db.schema import LightingStation3LightMeterCalibration
from src.model.db.schema import LightingStation3ParamRow
from src.model.db.schema import LightingStation3ResultRow
from src.model.vc_messages import StepFinishMessage
from src.model.vc_messages import StepMinorTextMessage
from src.model.vc_messages import StepProgressMessage
from src.model.vc_messages import StepStartMessage
from src.stations.lighting.station3.model import Station3Model
from src.stations.lighting.station3.model import Station3ModelBuilder
from src.stations.test_station import TestFailure
from src.stations.test_station import TestStation

log = logger(__name__)

__all__ = [
    'Station3',
]


class Station3(TestStation):
    model_builder_t = Station3ModelBuilder
    model_builder: Station3ModelBuilder
    model: Station3Model
    iteration_t = LightingStation3Iteration
    iteration: LightingStation3Iteration
    unit: LightingDUT

    ps = BKPowerSupply()
    lm = LightMeter()
    ftdi = RS485()

    _config = configuration.from_yml(r'lighting\station3\station.yml')
    light_meter_calibration_interval_hours = _config.field(int)
    power_supply_log_level = _config.field(int, transform=configuration.log_level)
    light_meter_log_level = _config.field(int, transform=configuration.log_level)
    ftdi_log_level = _config.field(int, transform=configuration.log_level)

    @instruments_joined
    def instruments_setup(self) -> None:
        self.ps.log_level(self.power_supply_log_level)
        self.ftdi.log_level(self.ftdi_log_level)
        self.lm.log_level(self.light_meter_log_level)
        with self.session_manager() as session:
            if not LightingStation3LightMeterCalibration.is_up_to_date(
                    session, self.light_meter_calibration_interval_hours
            ):
                self.ps.write_settings(DCLevel(0, 0), False)
                self.lm.calibrate()
                session.make(LightingStation3LightMeterCalibration())

    @instruments_spawned
    def string_test(self, params: LightingStation3ParamRow,
                    do_dmx: bool = True) -> Union[bool, LightingStation3ResultRow]:

        read_settings_promise = self.ps.read_settings()

        # noinspection PyNoneFunctionAssignment
        dmx_promise = self.ftdi.dmx_control(
            is_continuous=True, ch_value_d=params.dmx_control_dict
        ) if do_dmx else None

        # noinspection PyUnresolvedReferences
        initial_power_settings = read_settings_promise.resolve()

        dc_setting_promise = self.ps.ramp_up() if params.ramp else self.ps.write_settings(
            DCLevel(params.v, params.i), True
        )

        light_measurements: List[LightingStation3LightMeasurement] = []
        _duration = params.duration
        _test_step_k = self.model.step_ids.string_checks[params.id]

        self.emit(StepStartMessage(k=_test_step_k, minor_text=params.name, max_val=_duration))

        _emit = self.emit

        def consumer(sample: ThermalDropSample) -> None:
            model = LightingStation3LightMeasurement(pct_drop=sample.pct_drop, te=sample.te)
            light_measurements.append(_emit(model))
            _emit(StepProgressMessage(k=_test_step_k, value=min(_duration, sample.te)))

        try:
            # noinspection PyUnresolvedReferences
            first, last = self.lm.thermal_drop(
                params.fcd_nom * .05, params.duration, 2., consumer
            ).resolve()  # type: LightMeasurement, LightMeasurement

        except LightMeterError as e:
            raise TestFailure(str(e), _test_step_k)

        dc_setting_promise.resolve()
        # noinspection PyUnresolvedReferences
        power_meas = self.ps.measure(fresh=True).resolve()

        if dmx_promise is not None:
            # noinspection PyUnresolvedReferences
            dmx_promise.cancel()

        # noinspection PyUnresolvedReferences
        self.ps.write_settings(*initial_power_settings).resolve()

        percent_drop = last.percent_drop_from(first)
        cie_dist = last.distance_from(AttrDict(x=params.x_nom, y=params.y_nom))

        obj = LightingStation3ResultRow(
            param_row_id=params.id, x=last.x, y=last.y, fcd=last.fcd, CCT=last.CCT,
            duv=last.duv, p=power_meas.P, pct_drop=percent_drop, cie_dist=cie_dist,
            cie_pf=cie_dist <= params.color_dist_max, light_measurements=light_measurements,
            fcd_pf=test_nom_tol(params.fcd_nom, params.fcd_tol, last.fcd),
            p_pf=test_nom_tol(params.p_nom, params.p_tol, power_meas.P),
            pct_drop_pf=percent_drop <= params.pct_drop_max, t=datetime.now(),
        )
        obj.pf = obj.cie_pf and obj.fcd_pf and obj.p_pf and obj.pct_drop_pf

        self.emit(StepFinishMessage(k=_test_step_k, success=obj.pf))

        return self.emit(obj)

    @instruments_joined
    def configure(self, config: Configuration, wait_after: bool) -> EEPROMConfigIteration:
        config_model = self.iteration.add(EEPROMConfigIteration(config_id=config.config_id))
        _emit = self.emit
        _test_step_k = self.model.step_ids.initial_config if config.is_initial else \
            self.model.step_ids.final_config
        _num_registers = len(config.registers)

        self.emit(StepStartMessage(k=_test_step_k, minor_text='write', max_val=_num_registers * 2))

        def consumer(message: ConfigIncrement) -> None:
            if message.i == _num_registers:
                _emit(StepMinorTextMessage(k=_test_step_k, minor_text='confirm'))
            _emit(StepProgressMessage(k=_test_step_k, value=message.i))

        try:
            self.ftdi.wet_configure(config.registers, consumer, read_first=False)

        except RS485Error:
            raise TestFailure(
                f'{config.name} configuration failed (initial={config.is_initial})', _test_step_k
            )

        else:
            self.ftdi.wet_send_reset(wait_after=wait_after)
            config_model.success = True
            self.emit(StepFinishMessage(k=_test_step_k, success=True))

        return config_model

    @instruments_joined
    def unit_identity(self, unit: LightingDUT, do_write: bool) -> ConfirmUnitIdentityIteration:
        unit_identity_confirmation_model = self.iteration.add(ConfirmUnitIdentityIteration())
        _test_step_k = self.model.step_ids.unit_identity

        self.emit(StepStartMessage(k=_test_step_k))

        try:
            if do_write:
                self.emit(StepMinorTextMessage(k=_test_step_k, minor_text='write'))

                self.ftdi.wet_write_unit_identity(unit.sn, unit.mn)

            self.emit(StepMinorTextMessage(k=_test_step_k, minor_text='confirm'))

            if not self.ftdi.wet_confirm_unit_identity(unit.sn, unit.mn):
                raise TestFailure('failed to confirm unit identity: unit identity incorrect', _test_step_k)

        except WETCommandError:
            raise TestFailure('failed to confirm unit identity: comm failure', _test_step_k)

        else:
            unit_identity_confirmation_model.success = True
            self.emit(StepFinishMessage(k=_test_step_k, success=True))

        return unit_identity_confirmation_model

    @instruments_joined
    def perform_connection_check(self) -> None:
        connection = self.ps.calculate_connection_state(self.model.connection_calc_type)
        if not bool(connection):
            raise TestFailure(f'failed power connection check: {connection}')

        self.emit(connection)

        if self.model.firmware is not None:
            micro_state = self.ftdi.get_micro_state()
            if micro_state == MicroState.NO_BOOTLOADER:
                raise TestFailure('failed to establish communication with the chroma')

            self.emit(micro_state)

    @instruments_spawned
    def perform_test(self) -> None:
        remaining_rows = self.model.string_params_rows.copy()

        # program and thermal as indicated
        if self.model.firmware is not None:
            firmware_iteration_model = self.iteration.add(FirmwareIteration(
                firmware_id=self.model.firmware_object.version_id,
            ))
            _test_step_k = self.model.step_ids.firmware

            self.emit(StepStartMessage(k=_test_step_k))

            if self.model.firmware_force_overwrite or not self.ftdi.dta_is_programmed_correctly(
                    self.model.firmware_object.version
            ).resolve():

                self.emit(StepMinorTextMessage(k=_test_step_k, minor_text='erase'))

                if not self.ftdi.dta_erase_and_confirm().resolve():
                    raise TestFailure('failed to confirm FW erasure', _test_step_k)

                self.emit(StepStartMessage(
                    k=_test_step_k, minor_text='write', max_val=len(self.model.firmware_object.code)
                ))
                _emit = self.emit

                def consumer(message: FirmwareIncrement) -> None:
                    _emit(StepProgressMessage(k=_test_step_k, value=message.i))

                # noinspection PyNoneFunctionAssignment
                programming_promise = self.ftdi.dta_program_firmware(
                    self.model.firmware_object.code, self.model.firmware_object.version, consumer
                )

                if self.model.program_with_thermal:
                    thermal_row, *remaining_rows = remaining_rows
                    self.iteration.result_rows.append(self.string_test(thermal_row, False))

                # noinspection PyUnresolvedReferences
                programming_promise.resolve()
                if not self.ftdi.dta_is_programmed_correctly(self.model.firmware_object.version).resolve():
                    raise TestFailure('failed to confirm FW version after programming', _test_step_k)

            firmware_iteration_model.skipped = True
            self.emit(StepFinishMessage(k=_test_step_k, success=True))

        if self.model.initial_config is not None:
            self.configure(self.model.initial_config_object, True)

        if self.model.unit_identity is not None:
            self.unit_identity(self.unit, self.model.unit_identity)

        self.iteration.result_rows.extend(map(self.string_test, remaining_rows))

        if self.model.final_config is not None:
            self.configure(self.model.final_config_object, False)

        self.iteration.pf = all(map(attrgetter('pf'), self.iteration.result_rows))
        if not self.iteration.pf:
            raise TestFailure('failed light checks')

        self.emit(self.iteration)

    @classmethod
    def debug_test(cls, unit: LightingDUT) -> None:
        with logger:
            station = Station3(connect(echo_sql=False))
            station.instruments_setup()
            station.setup(unit)
            # station = station.proxy_spawn()
            # fake_promise: proxy.Promise = station.fake_long_method()
            # sleep(3.)
            # fake_promise.cancel()
            # station = station.proxy_join()
            # station.instruments_cleanup()

            try:
                while 1:
                    for f_name in ('connection_check', 'run'):
                        sleep(1.)
                        print('\n\n')
                        user_input = input(f'proceed with {f_name}? -> ')
                        if user_input.lower() != 'y':
                            return
                        print('\n\n')
                        getattr(station, f_name)()

            except KeyboardInterrupt:
                pass


if __name__ == '__main__':
    Station3.debug_test(LightingDUT(sn=12701575, mn=918, option='b'))
