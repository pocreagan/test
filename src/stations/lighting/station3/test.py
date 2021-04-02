from datetime import datetime
from operator import attrgetter
from typing import Dict
from typing import List
from typing import Optional
from typing import Type
from typing import Union

from attrdict import AttrDict

from src.base.actor import configuration
from src.base.general import test_nom_tol
from src.base.log import logger
from src.instruments.base.instrument import instruments_joined
from src.instruments.base.instrument import instruments_spawned
from src.instruments.dc_power_supplies import DCLevel
from src.instruments.dc_power_supplies.bk_ps import BKPowerSupply
from src.instruments.dc_power_supplies.connection_states import ConnectionState
from src.instruments.dc_power_supplies.connection_states import ConnectionStateCalcType
from src.instruments.light_meter import LightMeasurement
from src.instruments.light_meter import LightMeter
from src.instruments.light_meter import LightMeterError
from src.instruments.light_meter import ThermalDropSample
from src.instruments.wet.rs485 import RS485
from src.instruments.wet.rs485 import RS485Error
from src.instruments.wet.rs485 import WETCommandError
from src.model.db import connect
from src.model.db.schema import Configuration
from src.model.db.schema import ConfirmUnitIdentityIteration
from src.model.db.schema import EEPROMConfigIteration
from src.model.db.schema import FirmwareIteration
from src.model.db.schema import LightingStation3Iteration
from src.model.db.schema import LightingStation3LightMeasurement
from src.model.db.schema import LightingStation3LightMeterCalibration
from src.model.db.schema import LightingStation3ParamRow
from src.model.db.schema import LightingStation3ResultRow
from src.stations.lighting.station3.model import Station3Model
from src.stations.lighting.station3.model import Station3TestModel
from src.stations.test_station import DUTIdentityModel
from src.stations.test_station import TestFailure
from src.stations.test_station import TestStation

log = logger(__name__)


class Station3(TestStation):
    model_builder_t = Station3Model
    model_builder: Station3Model
    models: Dict[int, Dict[Optional[str], Station3TestModel]]
    model: Station3TestModel
    iteration: LightingStation3Iteration
    unit: DUTIdentityModel

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
        _emit = self.emit

        def consumer(sample: ThermalDropSample) -> None:
            model = LightingStation3LightMeasurement(fcd=sample.fcd, te=sample.te)
            light_measurements.append(model)
            _emit(model)

        light_measurement_promise = self.lm.thermal_drop(
            params.fcd_nom * .05, params.duration, 2., consumer
        )

        try:
            # noinspection PyUnresolvedReferences
            first, last = light_measurement_promise.resolve()  # type: LightMeasurement, LightMeasurement

        except LightMeterError as e:
            raise TestFailure(str(e))

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
        return self.emit(obj)

    @instruments_joined
    def configure(self, config: Configuration, wait_after: bool) -> EEPROMConfigIteration:
        config_model = EEPROMConfigIteration(config_id=config.config_id)
        self.iteration.config_iterations.append(config_model)
        try:
            self.ftdi.wet_configure(config.registers, self.emit, read_first=False)

        except RS485Error:
            raise TestFailure(f'{config.name} configuration failed (initial={config.is_initial})')

        else:
            self.ftdi.wet_send_reset(wait_after=wait_after)
            config_model.success = True

        return config_model

    @instruments_joined
    def unit_identity(self, unit: DUTIdentityModel, do_write: bool) -> ConfirmUnitIdentityIteration:
        unit_identity_confirmation_model = ConfirmUnitIdentityIteration()
        self.iteration.unit_identity_confirmations.append(unit_identity_confirmation_model)
        try:
            if do_write:
                self.ftdi.wet_write_unit_identity(unit.sn, unit.mn)

            if not self.ftdi.wet_confirm_unit_identity(unit.sn, unit.mn):
                raise TestFailure('failed to confirm unit identity: unit identity incorrect')

        except WETCommandError:
            raise TestFailure('failed to confirm unit identity: comm failure')

        else:
            unit_identity_confirmation_model.success = True

        return unit_identity_confirmation_model

    @instruments_joined
    def connection_state(self, calc: Type[ConnectionStateCalcType]) -> ConnectionState:
        connection = self.ps.calculate_connection_state(calc)
        if not bool(connection):
            raise TestFailure(f'failed connection state check: {connection}')

        return connection

    def iteration_setup(self, unit: DUTIdentityModel) -> None:
        self.unit = unit
        self.model = self.models.get(self.unit.mn).get(self.unit.option)

    @instruments_spawned
    def perform_test(self) -> LightingStation3Iteration:
        self.iteration = LightingStation3Iteration()

        remaining_rows = self.model.string_params_rows.copy()

        self.connection_state(self.model.connection_calc_type)

        # program and thermal as indicated
        if self.model.firmware is not None:
            # check for chroma communication, if no bootloader at least that's a test failure
            # noinspection PyUnresolvedReferences
            if not self.ftdi.wet_at_least_bootloader().resolve():
                raise TestFailure('failed to establish communication with the chroma')

            firmware_iteration_model = FirmwareIteration(
                firmware_id=self.model.firmware_object.version_id,
            )
            self.iteration.firmware_iterations.append(firmware_iteration_model)

            if self.model.firmware_force_overwrite or not self.ftdi.dta_is_programmed_correctly(
                    self.model.firmware_object.version
            ).resolve():
                if not self.ftdi.dta_erase_and_confirm().resolve():
                    raise TestFailure('failed to confirm FW erasure')

                # noinspection PyNoneFunctionAssignment
                programming_promise = self.ftdi.dta_program_firmware(
                    self.model.firmware_object.code, self.model.firmware_object.version, self.emit
                )
                if self.model.program_with_thermal:
                    thermal_row, *remaining_rows = remaining_rows
                    self.iteration.result_rows.append(self.string_test(thermal_row, False))

                # noinspection PyUnresolvedReferences
                programming_promise.resolve()
                if not self.ftdi.dta_is_programmed_correctly(self.model.firmware_object.version).resolve():
                    raise TestFailure('failed to confirm FW version after programming')

                firmware_iteration_model.success = True

            else:
                firmware_iteration_model.skipped = True

        if self.model.initial_config is not None:
            self.configure(self.model.initial_config_object, True)

        if self.model.unit_identity is not None:
            self.unit_identity(self.unit, self.model.unit_identity)

        self.iteration.result_rows.extend(map(self.string_test, remaining_rows))

        if self.model.final_config is not None:
            self.configure(self.model.final_config_object, False)

        self.iteration.pf = all(map(attrgetter('pf'), self.iteration.result_rows))
        return self.iteration

    @classmethod
    def debug_test(cls, unit: DUTIdentityModel) -> None:
        with logger:
            station = Station3(connect(echo_sql=True))
            station.instruments_setup()
            station.run(unit)


if __name__ == '__main__':
    Station3.debug_test(DUTIdentityModel(12701575, 918, 'b'))
