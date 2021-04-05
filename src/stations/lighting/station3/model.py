from dataclasses import dataclass
from dataclasses import field
from operator import attrgetter
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
from typing import Type

from src.base.db.connection import SessionManager
from src.base.db.connection import SessionType
from src.instruments.dc_power_supplies import connection_states
from src.instruments.dc_power_supplies.connection_states import ConnectionStateCalcType
from src.model import configuration
from src.model.db.schema import AppConfigUpdate
from src.model.db.schema import Configuration
from src.model.db.schema import EEPROMConfig
from src.model.db.schema import Firmware
from src.model.db.schema import FirmwareVersion
from src.model.db.schema import LightingDUT
from src.model.db.schema import LightingStation3Param
from src.model.db.schema import LightingStation3ParamRow
from src.model.db.schema import YamlFile

__all__ = [
    'Station3ModelBuilder',
    'Station3Model',
    'Station3ChartParamsModel',
]


@dataclass
class Station3ChartParamsModel:
    param_id: int
    mn: int
    rows: List[LightingStation3ParamRow]


@dataclass
class Station3StepIDs:
    firmware: Optional[int] = None
    initial_config: Optional[int] = None
    final_config: Optional[int] = None
    unit_identity: Optional[int] = None
    string_checks: Dict[int, int] = field(default_factory=dict)

    @property
    def for_view(self) -> Dict[int, str]:
        r = ((self.firmware, 'FIRMWARE'),
             (self.initial_config, 'INITIAL CFG'),
             (self.final_config, 'FINAL CFG'),
             (self.unit_identity, 'EEPROM'),)
        r += tuple((v, 'STRING') for v in self.string_checks.values())
        return {k: v for k, v in r if k is not None}


@dataclass
class Station3Model:
    config_rev: int
    connection_calc: str
    param_sheet: str
    chart: str
    firmware: Optional[str] = None
    unit_identity: Optional[bool] = None
    program_with_thermal: Optional[bool] = None
    cooldown_interval_s: Optional[float] = None
    initial_config: Optional[str] = None
    final_config: Optional[str] = None
    firmware_force_overwrite: bool = False
    connection_calc_type: Optional[Type[ConnectionStateCalcType]] = None
    initial_config_object: Optional[Configuration] = None
    final_config_object: Optional[Configuration] = None
    firmware_object: Optional[Firmware] = None
    params_obj: Optional[LightingStation3Param] = None
    string_params_rows: List[LightingStation3ParamRow] = field(default_factory=list)
    step_ids: Station3StepIDs = None


class Station3ModelBuilder:
    _config = configuration.from_yml(r'lighting\station3\models.yml')
    model_configs = _config.field(dict)
    built_model: Dict[int, Dict[Optional[str], Station3Model]] = None
    last_rev: int = 0

    def __init__(self, session_manager: SessionManager) -> None:
        self.session_manager = session_manager

    def __call__(self) -> Dict[int, Dict[Optional[str], Station3Model]]:
        with self.session_manager(expire=False) as session:
            latest_rev = AppConfigUpdate.get(session).id
            if latest_rev > self.last_rev:
                self.last_rev = latest_rev
                YamlFile.update_object(session, self)
                self.built_model = self.build_test_model(session)
        return self.built_model

    def for_dut(self, dut: LightingDUT) -> Tuple[Station3Model, Station3ChartParamsModel]:
        self()
        model = self.built_model[dut.mn][dut.option]
        chart = Station3ChartParamsModel(
            param_id=model.params_obj.id, mn=dut.mn, rows=model.string_params_rows
        )
        return model, chart

    def build_test_model(self, session: SessionType) -> Dict[int, Dict[Optional[str], Station3Model]]:
        model_dict = {}
        for mn, model_config in self.model_configs.items():
            model_dict[int(mn)]: Dict[Optional[str], Station3Model] = {
                opt: self.build_test_model_for_mn_option(
                    session, model_config, opt
                ) for opt in [None] + list(model_config.get('options', {}).keys())
            }
        # noinspection PyTypeChecker
        return model_dict

    def build_test_model_for_mn_option(
            self, session: SessionType, model_config: Dict[str, Any], option: Optional[str]
    ) -> Station3Model:
        _ = self
        config_dict: Dict[str, Any] = model_config.copy()
        if 'options' in config_dict:
            model_options = config_dict.pop('options')
            config_dict.update(model_options.get('default', {}))
            if option:
                config_dict.update(model_options.get(option, {}))
        model = Station3Model(config_rev=self.last_rev, **config_dict)
        model.step_ids = Station3StepIDs()
        model.params_obj = LightingStation3Param.get(session, model.param_sheet)
        model.string_params_rows = list(sorted(model.params_obj.rows, key=attrgetter('row_num')))
        model.connection_calc_type = getattr(connection_states, model.connection_calc)
        if (model.firmware_force_overwrite or model.program_with_thermal) and not model.firmware:
            raise ValueError(
                'fw version must be specified if firmware_force_overwrite or program_with_thermal'
            )
        _last_step_id = -1
        if model.firmware:
            model.firmware_object = FirmwareVersion.get(
                session, f'lighting\\firmware\\{model.firmware}.dta'
            )
            _last_step_id += 1
            model.step_ids.firmware = _last_step_id
        for final, cfg_name in enumerate(['initial_config', 'final_config']):
            cfg_sheet_name = getattr(model, cfg_name)
            if cfg_sheet_name is not None:
                config_object = EEPROMConfig.get(
                    session, cfg_sheet_name, is_initial=not bool(final)
                )
                eeprom_config = {} if final else {(0x5, i): 0x0 for i in range(34, 48)}
                eeprom_config.update(config_object.registers)
                config_object.registers = {k: eeprom_config[k] for k in sorted(eeprom_config)}
                setattr(model, f'{cfg_name}_object', config_object)
                _last_step_id += 1
                setattr(model.step_ids, cfg_name, _last_step_id)

        if model.unit_identity is not None:
            _last_step_id += 1
            model.step_ids.unit_identity = _last_step_id

        for row in model.string_params_rows:  # type: LightingStation3ParamRow
            _last_step_id += 1
            model.step_ids.string_checks[row.id] = _last_step_id

        return model
