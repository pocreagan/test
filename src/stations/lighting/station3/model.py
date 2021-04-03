from dataclasses import dataclass
from dataclasses import field
from operator import attrgetter
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Type

from src.model import configuration
from src.base.db.connection import SessionManager
from src.base.db.connection import SessionType
from src.instruments.dc_power_supplies import connection_states
from src.instruments.dc_power_supplies.connection_states import ConnectionStateCalcType
from src.model.db.schema import Configuration
from src.model.db.schema import EEPROMConfig
from src.model.db.schema import Firmware
from src.model.db.schema import FirmwareVersion
from src.model.db.schema import LightingStation3Param
from src.model.db.schema import YamlFile

__all__ = [
    'Station3TestModel',
    'Station3Model'
]


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
    params_obj: Optional[LightingStation3Param] = None
    string_params_rows: List[LightingStation3Param] = field(default_factory=list)


class Station3Model:
    _config = configuration.from_yml(r'lighting\station3\models.yml')
    model_configs = _config.field(dict)

    def __init__(self, session_manager: SessionManager) -> None:
        self.session_manager = session_manager

    def __call__(self) -> Dict[int, Dict[Optional[str], Station3TestModel]]:
        with self.session_manager() as session:
            YamlFile.update_object(session, self)
        # noinspection PyTypeChecker
        return self.build_test_model()

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
        model.params_obj = LightingStation3Param.get(session, model.param_sheet)
        model.string_params_rows = list(sorted(model.params_obj.rows, key=attrgetter('row_num')))
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
