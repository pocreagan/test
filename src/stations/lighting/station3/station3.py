import logging
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from time import perf_counter
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
from typing import Type

from src.base.general import test_nom_tol
from src.base.log import logger
from src.controller.test_station import TestStation
from src.instruments.base.instrument import instruments_joined
from src.instruments.base.instrument import instruments_spawned
from src.instruments.dc_power_supplies import DCLevel
from src.instruments.dc_power_supplies.bk_ps import BKPowerSupply
from src.instruments.dc_power_supplies.connection_states import ConnectionStateCalcType
from src.instruments.light_meter import LightMeter
from src.instruments.wet.rs485 import RS485
from src.instruments.wet.rs485 import RS485Error
from src.model.db.helper import dataclass_to_model
from src.model.db.schema import LightingStation3LightMeasurement
from src.model.db.schema import LightingStation3Param
from src.model.db.schema import LightingStation3ParamRow
from src.model.db.schema import LightingStation3ResultRow

log = logger(__name__)


# TODO: make station .yml for string check and test it with thrown errors
# TODO: optional view injection for updates with unified interface
# TODO: merge test_framework -> instruments
# TODO: config step model with one to one relationships to DUT, iteration, station, config


@dataclass
class Station3TestModel:
    connection_calc: Type[ConnectionStateCalcType]
    firmware: Optional[str]
    thermal_with_firmware: bool
    initial_config: Optional[str]
    final_config: Optional[str]
    string_params: List[LightingStation3Param] = field(default_factory=list)
    firmware_force_overwrite: bool = False


class Station3(TestStation):
    ps = BKPowerSupply()
    lm = LightMeter()
    ftdi = RS485()

    @instruments_joined
    def instruments_setup(self) -> None:
        self.ps.log_level(logging.INFO)
        self.ftdi.log_level(logging.INFO)
        self.lm.calibrate()

    @instruments_spawned
    def string_test(self, params: LightingStation3ParamRow,
                    do_dmx: bool = True) -> LightingStation3ResultRow:
        meas, tf = None, None
        light_measurements: List[LightingStation3LightMeasurement] = []

        read_settings_promise = self.ps.read_settings()
        if do_dmx:
            # noinspection PyUnresolvedReferences
            self.ftdi.dmx_control(is_continuous=False, ch_value_d=params.dmx_control_dict).resolve()

        # noinspection PyUnresolvedReferences
        initial_power_settings = read_settings_promise.resolve()

        dc_setting_promise = self.ps.ramp_up() if params.ramp else self.ps.write_settings(
            DCLevel(params.v, params.i), True
        )

        # noinspection PyUnresolvedReferences
        last_meas = self.lm.measure().resolve()
        while tf is None or perf_counter() < tf:

            # noinspection PyUnresolvedReferences
            meas = self.lm.measure().resolve()
            if tf is None:
                if meas.fcd < last_meas.fcd:
                    tf = perf_counter() + params.duration

            else:
                light_measurements.append(
                    self.emit(
                        dataclass_to_model(meas, LightingStation3LightMeasurement, t=datetime.now())
                    )
                )

        dc_setting_promise.resolve()
        # noinspection PyUnresolvedReferences
        power_meas = self.ps.measure(fresh=True).resolve().P

        # noinspection PyUnresolvedReferences
        self.ps.write_settings(*initial_power_settings).resolve()

        percent_drop = meas.percent_drop_from(light_measurements[0])

        return self.station.emit(
            LightingStation3ResultRow(
                x=meas.x, y=meas.y, fcd=meas.fcd, cct=meas.cct, duv=meas.duv, p=power_meas,
                pct_drop=percent_drop, cie_dist=meas.distance_from(params.cie_dist),
                cie_pf=meas.distance_from(params) <= params.color_dist_max,
                fcd_pf=test_nom_tol(params.fcd_nom, params.fcd_tol, meas.fcd),
                p_pf=test_nom_tol(params.p_nom, params.p_tol, power_meas),
                pct_drop_pf=percent_drop <= params.pct_drop_max,
                light_measurements=light_measurements, t=datetime.now(),
            )
        )

    def configure(self, config: Dict[Tuple[int, int], int], wait_after: bool) -> bool:
        try:
            # noinspection PyUnresolvedReferences
            self.ftdi.wet_configure(config, self.station.emit, read_first=True).resolve()
        except RS485Error:
            return False
        else:
            # noinspection PyUnresolvedReferences
            self.ftdi.wet_send_reset(wait_after=wait_after).resolve()
            return True

    def perform_test(self) -> bool:
        remaining_rows = self.model.string_params.copy()
        result_rows: List[LightingStation3ResultRow] = []

        # check connection
        if not bool(self.ps.calculate_connection_state(self.model.connection_calc)):
            return self.test_failure('failed connection state check')

        # program and thermal as indicated
        if self.model.firmware is not None:
            # check for chroma communication, if no bootloader at least that's a test failure
            if not self.ftdi.wet_at_least_bootloader().resolve():
                return self.test_failure('failed to establish communication with the chroma')

            programming_promise = None

            if not self.ftdi.dta_is_programmed_correctly(self.model.firmware).resolve():
                if not self.ftdi.dta_erase_and_confirm().resolve():
                    return self.test_failure('failed to confirm FW erasure')

                # noinspection PyNoneFunctionAssignment
                programming_promise = self.ftdi.dta_program_firmware(self.model.firmware, self.station.emit)

            if self.model.thermal_with_firmware:
                thermal_row, *remaining_rows = remaining_rows
                result_rows.append(self.string_test(thermal_row, False))

            if programming_promise is not None:
                # noinspection PyUnresolvedReferences
                programming_promise.resolve()
                if not self.ftdi.dta_is_programmed_correctly(self.model.firmware).resolve():
                    return self.test_failure('failed to confirm FW version after programming')

        # write/confirm SN and MN if indicated
        if self.model.unit_identity is not None:
            if self.model.unit_identity:
                self.ftdi.wet_write_unit_identity(self.unit.sn, self.unit.mn)
            if not self.ftdi.wet_confirm_unit_identity(self.unit.sn, self.unit.mn):
                return self.test_failure('failed to confirm unit identity')

        # initial config
        if self.model.initial_config is not None:
            if not self.configure(self.model.initial_config, True):
                return self.test_failure('failed to confirm EEPROM initial config')

        # non-full on string check steps
        result_rows.extend(map(self.string_test, remaining_rows))

        # final config
        if self.model.final_config is not None:
            if not self.configure(self.model.final_config, False):
                return self.test_failure('failed to confirm EEPROM final config')

        return True


if __name__ == '__main__':
    with logger:
        pass
