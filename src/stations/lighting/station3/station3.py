from collections import deque
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from operator import itemgetter
from time import perf_counter
from time import sleep
from typing import Any
from typing import Deque
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
from typing import Type
from typing import Union

from attrdict import AttrDict

from instruments.wet.rs485 import WETCommandError
from model.db.schema import Configuration
from model.db.schema import ConfirmUnitIdentityIteration
from model.db.schema import EEPROMConfigIteration
from model.db.schema import Firmware
from model.db.schema import FirmwareIteration
from model.db.schema import FirmwareVersion
from model.db.schema import LightingStation3Iteration
from src.base.actor import configuration
from src.base.db.connection import SessionType
from src.base.general import test_nom_tol
from src.base.log import logger
from src.instruments.base.instrument import instruments_joined
from src.instruments.base.instrument import instruments_spawned
from src.instruments.dc_power_supplies import connection_states
from src.instruments.dc_power_supplies import DCLevel
from src.instruments.dc_power_supplies.bk_ps import BKPowerSupply
from src.instruments.dc_power_supplies.connection_states import ConnectionStateCalcType
from src.instruments.light_meter import LightMeasurement
from src.instruments.light_meter import LightMeter
from src.instruments.wet.rs485 import RS485
from src.instruments.wet.rs485 import RS485Error
from src.model.db import connect
from src.model.db.schema import EEPROMConfig
from src.model.db.schema import LightingStation3LightMeasurement
from src.model.db.schema import LightingStation3LightMeterCalibration
from src.model.db.schema import LightingStation3Param
from src.model.db.schema import LightingStation3ParamRow
from src.model.db.schema import LightingStation3ResultRow
from src.model.db.schema import TestIterationProtocol
from src.stations.test_station import DUTIdentityModel
from src.stations.test_station import TestStation

log = logger(__name__)


@dataclass
class Station3TestModel:
    connection_calc: str
    param_sheet: str
    chart: str
    firmware: Optional[str] = None
    unit_identity: Optional[bool] = None
    program_with_thermal: Optional[bool] = None
    initial_config: Optional[str] = None
    final_config: Optional[str] = None
    firmware_force_overwrite: bool = False
    connection_calc_type: Optional[Type[ConnectionStateCalcType]] = None
    initial_config_object: Optional[Configuration] = None
    final_config_object: Optional[Configuration] = None
    firmware_object: Optional[Firmware] = None
    string_params_rows: List[LightingStation3Param] = field(default_factory=list)


class Station3(TestStation):
    model: Dict[int, Dict[Optional[str], Station3TestModel]]

    def get_test_iteration(self) -> TestIterationProtocol:
        raise NotImplementedError

    def build_test_model(self) -> Dict[int, Dict[Optional[str], Station3TestModel]]:
        model_dict = {}
        with self.session_manager(expire=False) as session:
            for mn, model_config in self.model_configs.items():
                model_dict[int(mn)]: Dict[Optional[str], Station3TestModel] = {
                    opt: self.build_test_model_for_mn_option(
                        session, model_config, opt
                    ) for opt in [None] + list(model_config.get('options', {}).keys())
                }
        # noinspection PyTypeChecker
        return model_dict

    def build_test_model_for_mn_option(
            self, session: SessionType, model_config: Dict[str, Any], option: Optional[str]
    ) -> Station3TestModel:
        _ = self
        config_dict: Dict[str, Any] = model_config.copy()
        if 'options' in config_dict:
            model_options = config_dict.pop('options')
            config_dict.update(model_options.get('default', {}))
            if option:
                config_dict.update(model_options.get(option, {}))
        model = Station3TestModel(**config_dict)
        model.string_params_rows = LightingStation3Param.get(session, model.param_sheet)
        model.connection_calc_type = getattr(connection_states, model.connection_calc)
        for initial, cfg_name in enumerate(['final_config', 'initial_config']):
            cfg_sheet_name = getattr(model, cfg_name)
            if cfg_sheet_name is not None:
                config_object = EEPROMConfig.get(session, cfg_sheet_name, is_initial=bool(initial))
                eeprom_config = {(0x5, i): 0x0 for i in range(34, 48)} if initial else {}
                eeprom_config.update(config_object.registers)
                config_object.registers = {k: eeprom_config[k] for k in sorted(eeprom_config)}
                setattr(model, f'{cfg_name}_object', config_object)
        if (model.firmware_force_overwrite or model.program_with_thermal) and not model.firmware:
            raise ValueError(
                'fw version must be specified if firmware_force_overwrite or program_with_thermal'
            )
        if model.firmware:
            model.firmware_object = FirmwareVersion.get(session, f'lighting\\firmware\\{model.firmware}.dta')
        return model

    ps = BKPowerSupply()
    lm = LightMeter()
    ftdi = RS485()

    _config = configuration.from_yml(r'lighting\station3\station3.yml')
    light_meter_calibration_interval_hours = _config.field(int)
    power_supply_log_level = _config.field(int, transform=configuration.log_level)
    light_meter_log_level = _config.field(int, transform=configuration.log_level)
    ftdi_log_level = _config.field(int, transform=configuration.log_level)
    model_configs = _config.field(dict)

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
    def string_test(self, iteration: LightingStation3Iteration, params: LightingStation3ParamRow,
                    do_dmx: bool = True) -> Union[bool, LightingStation3ResultRow]:
        meas, tf, dmx_promise, last_measurement, first_meas, first_t = None, None, None, None, None, None
        light_measurements: List[LightingStation3LightMeasurement] = []

        read_settings_promise = self.ps.read_settings()
        if do_dmx:
            # noinspection PyNoneFunctionAssignment
            dmx_promise = self.ftdi.dmx_control(
                is_continuous=False, ch_value_d=params.dmx_control_dict
            )

        # noinspection PyUnresolvedReferences
        initial_power_settings = read_settings_promise.resolve()

        dc_setting_promise = self.ps.ramp_up() if params.ramp else self.ps.write_settings(
            DCLevel(params.v, params.i), True
        )

        # noinspection PyUnresolvedReferences
        last_meas = meas = self.lm.measure().resolve()
        timeout = perf_counter() + 1.
        rolling_meas: Deque[Tuple[LightMeasurement, datetime]] = deque(maxlen=3)
        while 1:
            if tf is None:
                if meas.fcd < last_meas.fcd and last_meas.fcd > (params.fcd_nom * .05):
                    tf = perf_counter() + params.duration
                else:
                    last_meas = meas
                    if perf_counter() > timeout:
                        return self.test_failure('string check illuminance ramp timeout reached')

            if tf is not None:
                rolling_meas.append((meas, datetime.now()))
                num_meas = len(rolling_meas)
                if num_meas > 1:
                    if num_meas == 2:
                        _meas, _t = rolling_meas[0]
                        first_meas = _meas
                        first_t = _t
                    else:
                        to_be_averaged = list(map(itemgetter(0), rolling_meas))
                        # noinspection PyTypeChecker
                        _meas, _t = LightMeasurement.averaged_from(to_be_averaged), rolling_meas[1][1]
                        last_measurement = _meas
                    light_measurements.append(
                        self.emit(LightingStation3LightMeasurement(
                            fcd=_meas.fcd, te=(_t - first_t).total_seconds()
                        ))
                    )
                if perf_counter() > tf:
                    break

            # noinspection PyUnresolvedReferences
            meas: Optional[LightMeasurement] = self.lm.measure().resolve()

        if dmx_promise is not None:
            # noinspection PyUnresolvedReferences
            dmx_promise.resolve()
        dc_setting_promise.resolve()
        # noinspection PyUnresolvedReferences
        power_meas = self.ps.measure(fresh=True).resolve()

        # noinspection PyUnresolvedReferences
        self.ps.write_settings(*initial_power_settings).resolve()

        percent_drop = last_measurement.percent_drop_from(first_meas)
        cie_dist = last_measurement.distance_from(AttrDict(x=params.x_nom, y=params.y_nom))

        result_model = self.emit(
            self.session.make(LightingStation3ResultRow(
                param_row_id=params.id,
                x=last_measurement.x, y=last_measurement.y, fcd=last_measurement.fcd,
                CCT=last_measurement.CCT, duv=last_measurement.duv,
                p=power_meas.P, pct_drop=percent_drop, cie_dist=cie_dist,
                cie_pf=cie_dist <= params.color_dist_max,
                fcd_pf=test_nom_tol(params.fcd_nom, params.fcd_tol, last_measurement.fcd),
                p_pf=test_nom_tol(params.p_nom, params.p_tol, power_meas.P),
                pct_drop_pf=percent_drop <= params.pct_drop_max,
                light_measurements=light_measurements, t=datetime.now(),
            ))
        )
        iteration.result_rows.append(result_model)
        return result_model

    @instruments_joined
    def configure(self, iteration: LightingStation3Iteration, config: Configuration,
                  wait_after: bool) -> bool:
        config_model = self.session.make(EEPROMConfigIteration(
            config_id=config.config_id
        ))
        try:
            self.ftdi.wet_configure(config.registers, self.emit, read_first=True)

        except RS485Error:
            config_model.success = False

        else:
            self.ftdi.wet_send_reset(wait_after=wait_after)
            config_model.success = True

        if config.is_initial:
            iteration.initial_config = config_model
        else:
            iteration.final_config = config_model

        return config_model.success

    def confirm_unit_identity(self, iteration: LightingStation3Iteration, unit: DUTIdentityModel) -> bool:
        iteration.unit_identity_confirmation = self.session.make(
            ConfirmUnitIdentityIteration()
        )
        try:
            iteration.unit_identity_confirmation.success = self.ftdi.wet_confirm_unit_identity(
                unit.sn, unit.mn
            )
            return True
        except WETCommandError:
            return False

    @instruments_spawned
    def perform_test(self, unit: DUTIdentityModel) -> bool:
        model = self.model.get(unit.mn).get(unit.option)
        remaining_rows = model.string_params_rows.copy()
        result_rows: List[LightingStation3ResultRow] = []
        iteration_model = self.session.make(LightingStation3Iteration())

        # check connection
        if not bool(self.ps.calculate_connection_state(model.connection_calc_type)):
            return self.test_failure('failed connection state check')

        # program and thermal as indicated
        if model.firmware is not None:
            # check for chroma communication, if no bootloader at least that's a test failure
            # noinspection PyUnresolvedReferences
            if not self.ftdi.wet_at_least_bootloader().resolve():
                return self.test_failure('failed to establish communication with the chroma')

            programming_promise = None
            iteration_model.firmware_iteration = self.session.make(FirmwareIteration(
                firmware_id=model.firmware_object.version_id,
            ))

            if not self.ftdi.dta_is_programmed_correctly(model.firmware_object.version).resolve():
                if not self.ftdi.dta_erase_and_confirm().resolve():
                    return self.test_failure('failed to confirm FW erasure')

                # noinspection PyNoneFunctionAssignment
                programming_promise = self.ftdi.dta_program_firmware(
                    model.firmware_object.code, model.firmware_object.version, self.emit
                )

            else:
                iteration_model.firmware_iteration.skipped = True

            if model.program_with_thermal:
                thermal_row, *remaining_rows = remaining_rows
                self.string_test(iteration_model, thermal_row, False)

            if programming_promise is not None:
                # noinspection PyUnresolvedReferences
                programming_promise.resolve()
                if not self.ftdi.dta_is_programmed_correctly(model.firmware_object.version).resolve():
                    return self.test_failure('failed to confirm FW version after programming')
                else:
                    iteration_model.firmware_iteration.success = True

        # write/confirm SN and MN if indicated
        if model.unit_identity is not None:
            if model.unit_identity:
                self.ftdi.wet_write_unit_identity(unit.sn, unit.mn)
            if not self.confirm_unit_identity(iteration_model, unit):
                return self.test_failure('failed to confirm unit identity')

        # initial config
        if model.initial_config is not None:
            if self.configure(iteration_model, model.initial_config_object, True):
                return self.test_failure('failed to confirm EEPROM initial config')

        # non-full on string check steps
        [self.string_test(iteration_model, row) for row in remaining_rows]

        # final config
        if model.final_config is not None:
            if not self.configure(iteration_model, model.final_config_object, False):
                return self.test_failure('failed to confirm EEPROM final config')

        return True

    def debug_test(self) -> None:
        try:
            unit = DUTIdentityModel(9000000, 918, 'b')
            model = self.model.get(unit.mn).get(unit.option)
            self.ps.calculate_connection_state(model.connection_calc_type)
            #
            # self.ftdi.dta_is_programmed_correctly(2746)
            # self.ftdi.dta_erase_and_confirm()
            # self.ftdi.dta_is_programmed_correctly(2746)
            # self.ftdi.dta_program_firmware(
            #     model.firmware_object.code, model.firmware_object.version, self.emit
            # )
            # sleep(.7)
            #
            # self.ftdi.dta_is_programmed_correctly(2746)
            #
            # print('config_result', self.configure(model.initial_config_registers, wait_after=True))

            result = self.string_test(model.string_params_rows[0], True)
            sleep(1.)
            list(map(print, result.light_measurements))
            sleep(1.)

        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    with logger:
        station = Station3(connect(echo_sql=False))
        station.instruments_setup()
        station.debug_test()
