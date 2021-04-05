"""
declarative models should inherit from (meta.Base, meta.TableMixin)
default factories should be declared in helper.py
"""
import datetime
import json
import re
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
from typing import Type
from typing import TypeVar
from typing import Union

import funcy
from sqlalchemy import Column
from sqlalchemy import func
from sqlalchemy import UniqueConstraint
from sqlalchemy.ext.declarative import DeclarativeMeta
from sqlalchemy.sql.selectable import ScalarSelect
from sqlalchemy.sql.sqltypes import Boolean
from sqlalchemy.sql.sqltypes import DateTime
from sqlalchemy.sql.sqltypes import Enum
from sqlalchemy.sql.sqltypes import Float
from sqlalchemy.sql.sqltypes import Integer
from sqlalchemy.sql.sqltypes import LargeBinary
from sqlalchemy.sql.sqltypes import String
from sqlalchemy.sql.sqltypes import Text

from src.base.db.connection import SessionType
from src.base.db.meta import *
from src.model.configuration import get_configs_on_object
from src.model.enums import *

__all__ = [
    'Schema',
    'AppConfigUpdate',
    'ConfigFile',
    'LightingStation1ResultRow',
    'YamlFile',
    'LightingDUT',
    'Configuration',
    'EEPROMConfig',
    'EEPROMRegister',
    'EEPROMConfigIteration',
    'ConfirmUnitIdentityIteration',
    'LightingStation3Iteration',
    'LightingStation3Param',
    'LightingStation3ParamRow',
    'LightingStation3LightMeasurement',
    'LightingStation3ResultRow',
    'LightingStation3LightMeterCalibration',
    'PartNumber',
    'Device',
    'Station',
    'Firmware',
    'FirmwareVersion',
    'FirmwareCode',
    'FirmwareIteration',
]

db_string = "postgres://postgres:wet_post_evaserv_69@10.40.20.77/postgres"


class Rel:
    pn_to_device = Relationship.one_to_many('PartNumber', 'devices', 'Device', 'part')
    device_to_config_iterations = Relationship.one_to_many('Device', 'config_iterations',
                                                           'EEPROMConfigIteration', 'dut')
    device_to_firmware_iterations = Relationship.one_to_many('Device', 'firmware_iterations',
                                                             'FirmwareIteration',
                                                             'dut')
    device_to_test_step_iterations = Relationship.one_to_many('Device', 'test_step_iterations',
                                                              'EEPROMConfigIteration',
                                                              'dut')
    lighting_station3_result_row_to_light_measurements = Relationship.one_to_many(
        'LightingStation3ResultRow',
        'light_measurements',
        'LightingStation3LightMeasurement',
        'result_row'
    )
    lighting_station3_iteration_results = Relationship.one_to_many(
        'LightingStation3Iteration', 'result_rows',
        'LightingStation3ResultRow',
        'test_iteration'
    )
    lighting_dut_station3_iterations = Relationship.one_to_many(
        'LightingDUT', 'lighting_station3_iterations',
        'LightingStation3Iteration', 'dut',
    )
    version_to_code = Relationship.one_to_one('FirmwareVersion', 'code', 'FirmwareCode', 'version')


Schema: Union[DeclarativeMeta, Type[TableMixin]] = declarative_base_factory('main')

lighting_station3_unit_identity_confirmation_association = Relationship.association(
    Schema, 'LightingStation3Iteration', 'unit_identity_confirmations',
    'ConfirmUnitIdentityIteration', 'lighting_station3_iteration',
)
lighting_station3_firmware_iteration_association = Relationship.association(
    Schema, 'LightingStation3Iteration', 'firmware_iterations',
    'FirmwareIteration', 'lighting_station3_iteration',
)
lighting_station3_config_iteration_association = Relationship.association(
    Schema, 'LightingStation3Iteration', 'config_iterations',
    'EEPROMConfigIteration', 'lighting_station3_iteration',
)


class AppConfigUpdate(Schema):
    _repr_fields = ['created_at']
    commit = Column(String(40), nullable=False)
    objects = Column(Text)

    @classmethod
    def rev(cls, session: SessionType, rev: int = None) -> Union[ScalarSelect, int]:
        if rev is None:
            return session.query(func.max(cls.id)).scalar_subquery()
        return rev

    @classmethod
    def get(cls, session: SessionType, rev: int = None) -> 'AppConfigUpdate':
        return session.query(cls).filter(cls.id == cls.rev(session, rev)).one()


class ConfigFile(Schema):
    _repr_fields = ['fp', 'last_modified']
    fp = Column(String(256), nullable=False)
    last_modified = Column(DateTime, nullable=False)
    children = Column(Text)


class LightingStation3LightMeterCalibration(Schema):
    _repr_fields = ['created_at']

    @classmethod
    def is_up_to_date(cls, session: SessionType, interval_hours: int) -> bool:
        return session.query(cls).filter(
            cls.created_at > (datetime.datetime.now() - datetime.timedelta(hours=interval_hours))
        ).first() is not None


class YamlFile(Schema):
    _repr_fields = ['fp', 'created_at']
    rev = Column(Integer, nullable=False)
    fp = Column(String(256), nullable=False)
    content = Column(Text, nullable=False)

    @classmethod
    def get(cls, session: SessionType, fp: str) -> Dict[str, Any]:
        result: Optional[YamlFile] = session.query(cls).filter(
            cls.fp == fp, cls.rev == AppConfigUpdate.rev(session)
        ).one_or_none()
        if not result:
            raise ValueError(f'{fp} deprecated or not present in the {cls.__name__} table')
        return json.loads(result.content)

    @classmethod
    def update_object(cls, session: SessionType, obj) -> None:
        [_c.update_from(
            cls.get(session, _c.original_fp)
        ) for _c in get_configs_on_object(obj)]


lighting_station3_rows_association_table = Relationship.association(
    Schema, 'LightingStation3Param', 'rows', 'LightingStation3ParamRow', 'params',
)


class LightingDUT(Schema):
    _repr_fields = ['sn', 'mn', 'option']
    # TODO: LightingDUT should have a unique constraint in production
    # sn = Column(Integer, nullable=False, unique=True)
    sn = Column(Integer, nullable=False)
    mn = Column(Integer, nullable=False)
    option = Column(String(128), nullable=True)
    lighting_station3_iterations = Rel.lighting_dut_station3_iterations.parent

    @classmethod
    def get_or_make(cls, session: SessionType, sn: int, mn: int, option: str) -> 'LightingDUT':
        result = session.query(cls).filter_by(sn=sn).one_or_none()
        if result is None:
            result = session.make(cls(sn=sn, mn=mn, option=option))
        return result


class LightingStation3Param(Schema):
    _repr_fields = ['name']
    rev = Column(Integer, nullable=False)
    name = Column(String(128), nullable=False)
    rows = lighting_station3_rows_association_table.parent

    @classmethod
    def get(cls, session: SessionType, name: str) -> 'LightingStation3Param':
        result = session.query(cls).filter(
            cls.name == name, cls.rev == AppConfigUpdate.rev(session)
        ).one_or_none()
        if not result:
            raise ValueError(f'{name} deprecated or not present in the {cls.__name__} table')
        return result


class LightingStation3ParamRow(Schema):
    _repr_fields = ['dmx_control_dict', 'x_nom', 'y_nom', 'color_dist_max', 'fcd_nom',
                    'fcd_tol', 'p_nom', 'p_tol', 'pct_drop_max']
    param_id = LightingStation3Param.id_fk()
    params = lighting_station3_rows_association_table.child
    row_num = Column(Integer, nullable=False)
    name = Column(String(128), nullable=False)
    v = Column(Float, nullable=False)
    i = Column(Float, nullable=False)
    ramp = Column(Boolean, nullable=False)
    dmx_ch1 = Column(Float, nullable=False)
    dmx_ch2 = Column(Float, nullable=False)
    dmx_ch3 = Column(Float, nullable=False)
    dmx_ch4 = Column(Float, nullable=False)
    dmx_ch5 = Column(Float, nullable=False)
    dmx_ch6 = Column(Float, nullable=False)
    dmx_ch7 = Column(Float, nullable=False)
    dmx_ch8 = Column(Float, nullable=False)
    dmx_ch9 = Column(Float, nullable=False)
    dmx_ch10 = Column(Float, nullable=False)
    duration = Column(Float, nullable=False)
    x_nom = Column(Float, nullable=False)
    y_nom = Column(Float, nullable=False)
    color_dist_max = Column(Float, nullable=False)
    fcd_nom = Column(Float, nullable=False)
    fcd_tol = Column(Float, nullable=False)
    p_nom = Column(Float, nullable=False)
    p_tol = Column(Float, nullable=False)
    pct_drop_max = Column(Float, nullable=False)

    @property
    def dmx_control_dict(self) -> Dict[int, float]:
        return {ch: getattr(self, f'dmx_ch{ch}') for ch in range(1, 11) if getattr(self, f'dmx_ch{ch}') != 0}


register_association_table = Relationship.association(
    Schema, 'EEPROMConfig', 'registers', 'EEPROMRegister', 'configs'
)


@dataclass
class Configuration:
    config_id: int
    name: str
    is_initial: bool
    registers: Dict[Tuple[int, int], int] = field(repr=False)


class EEPROMConfig(Schema):
    rev = Column(Integer, nullable=False)
    is_initial = Column(Boolean)
    name = Column(String(128), nullable=False)
    registers: Any = register_association_table.parent

    @classmethod
    def get(cls, session: SessionType, name: str, is_initial: bool) -> Configuration:
        result = session.query(cls).filter(
            cls.name == name, cls.is_initial == is_initial, cls.rev == AppConfigUpdate.rev(session)
        ).one_or_none()
        if not result:
            raise ValueError(
                f'{name} <initial={is_initial}> deprecated or not present in the {cls.__name__} table'
            )
        return Configuration(
            result.id, result.name, result.is_initial, {
                (reg.target, reg.index): reg.value for reg in result.registers
            }
        )


class EEPROMRegister(Schema):
    _repr_fields = ['target', 'index', 'value', ]
    config_id = EEPROMConfig.id_fk()
    configs = register_association_table.child
    target = Column(Integer, nullable=False)
    index = Column(Integer, nullable=False)
    value = Column(Integer, nullable=False)

    __table_args__ = (UniqueConstraint('target', 'index', 'value'),)


class PartNumber(Schema):
    _repr_fields = ['string', ]
    string = Column(String(128), unique=True, nullable=False)
    devices = Rel.pn_to_device.parent


class Device(Schema):
    _repr_fields = ['sn', ]
    pn_id = PartNumber.id_fk()
    sn = Column(Integer, nullable=False)
    uid = Column(String(16), nullable=True)
    part = Rel.pn_to_device.child
    # config_iterations = Rel.device_to_config_iterations.parent
    # firmware_iterations = Rel.device_to_firmware_iterations.parent
    # test_iterations = Rel.device_to_test_iterations.parent
    # test_step_iterations = Rel.device_to_test_step_iterations.parent
    # release = Rel.device_to_released_device.parent


class Station(Schema):
    _repr_fields = ['name', ]
    pc_name = Column(String(128), nullable=False, unique=True)
    name = Column(String(64), unique=True, nullable=False)


firmware_association_table = Relationship.association(
    Schema, 'FirmwareVersion', 'code', 'FirmwareCode', 'version'
)


@dataclass
class Firmware:
    version_id: int
    name: str
    version: int
    code: List[bytes] = field(repr=False)


class FirmwareVersion(Schema):
    _repr_fields = ['name', 'version', ]
    fp_to_fields_re = re.compile(r'(?i)(\d+)\.dta')

    rev = Column(Integer, nullable=False)
    name = Column(String(128), nullable=False)
    version = Column(Integer, nullable=False)
    code = firmware_association_table.parent

    @classmethod
    def get(cls, session: SessionType, name: str) -> Firmware:
        result = session.query(cls).filter(
            cls.name == name, cls.rev == AppConfigUpdate.rev(session)
        ).one_or_none()
        if not result:
            raise ValueError(f'{name} deprecated or not present in the {cls.__name__} table')
        return Firmware(result.id, result.name, result.version, result.code[0].in_chunks)


class FirmwareCode(Schema):
    _repr_fields = ['hash', ]
    fw_id = FirmwareVersion.id_fk()
    code = Column(LargeBinary, nullable=False)
    hashed = Column(String(32), nullable=False)
    version = firmware_association_table.child

    @property
    def in_chunks(self) -> List[bytes]:
        return list(map(bytes, funcy.chunks(271, map(int, self.code))))


class EEPROMConfigIteration(Schema):
    _repr_fields = ['config', 'success', 'created_at', ]
    config_id = EEPROMConfig.id_fk()
    config = Relationship.child_to_parent(EEPROMConfig)
    success = Column(Boolean, default=False)

    lighting_station3_iteration = lighting_station3_config_iteration_association.child


class ConfirmUnitIdentityIteration(Schema):
    _repr_fields = ['success', 'created_at', ]
    success = Column(Boolean, default=False)

    lighting_station3_iteration = lighting_station3_unit_identity_confirmation_association.child


class FirmwareIteration(Schema):
    _repr_fields = ['firmware', 'skipped', 'success', 'created_at', ]
    firmware_id = FirmwareVersion.id_fk()
    firmware = Relationship.child_to_parent(FirmwareVersion)
    skipped = Column(Boolean, default=False)
    success = Column(Boolean, default=False)

    lighting_station3_iteration = lighting_station3_firmware_iteration_association.child


light_measurement_association_table = Relationship.association(
    Schema, 'LightingStation3ResultRow', 'light_measurements',
    'LightingStation3LightMeasurement', 'result_row'
)

_T = TypeVar('_T')


class LightingStation3Iteration(Schema):
    _repr_fields = ['p_f', 'created_at']
    dut_id = LightingDUT.id_fk()
    dut = Rel.lighting_dut_station3_iterations.child
    unit_identity_confirmations = lighting_station3_unit_identity_confirmation_association.parent
    firmware_iterations = lighting_station3_firmware_iteration_association.parent
    config_iterations = lighting_station3_config_iteration_association.parent
    result_rows = Rel.lighting_station3_iteration_results.parent
    pf = Column(Boolean, default=False)

    __collection_map = {'LightingStation3ResultRow': 'result_rows',
                        'ConfirmUnitIdentityIteration': 'unit_identity_confirmations',
                        'FirmwareIteration': 'firmware_iterations',
                        'EEPROMConfigIteration': 'config_iterations', }

    def add(self, obj: _T) -> _T:
        getattr(self, self.__collection_map[type(obj).__name__]).append(obj)
        return obj


class LightingStation3ResultRow(Schema):
    _repr_fields = ['x', 'y', 'fcd', 'p', 'pct_drop', ]
    param_row_id = LightingStation3ParamRow.id_fk()
    param_row = Relationship.child_to_parent(LightingStation3ParamRow)
    test_iteration_id = LightingStation3Iteration.id_fk()
    test_iteration = Rel.lighting_station3_iteration_results.child
    light_measurements = Rel.lighting_station3_result_row_to_light_measurements.parent
    t = Column(DateTime, nullable=False)
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)
    fcd = Column(Float, nullable=False)
    CCT = Column(Float, nullable=False)
    duv = Column(Float, nullable=False)
    p = Column(Float, nullable=False)
    pct_drop = Column(Float, nullable=False)
    cie_dist = Column(Float, nullable=False)
    cie_pf = Column(Boolean, default=False)
    fcd_pf = Column(Boolean, default=False)
    p_pf = Column(Boolean, default=False)
    pct_drop_pf = Column(Boolean, default=False)
    pf = Column(Boolean, default=False)


class LightingStation3LightMeasurement(Schema):
    _repr_fields = ['te', 'fcd', ]
    result_row_id = LightingStation3ResultRow.id_fk()
    result_row = Rel.lighting_station3_result_row_to_light_measurements.child
    pct_drop = Column(Float, nullable=False)
    te = Column(Float, nullable=False)


class LightingStation1ResultRow(Schema):
    _repr_fields = ['row_num', 'v', 'i', 'p', 'hipot_v', 'knee_v', ]
    row_num = Column(Integer, nullable=False)
    v = Column(Float, nullable=False)
    i = Column(Float, nullable=False)
    p = Column(Float, nullable=False)
    hipot_v = Column(Float, nullable=False)
    knee_v = Column(Float, nullable=False)
    v_pf = Column(Boolean, default=False)
    i_pf = Column(Boolean, default=False)
    p_pf = Column(Boolean, default=False)
    hipot_v_pf = Column(Boolean, default=False)
    knee_v_pf = Column(Boolean, default=False)


class LeakTesterMeasurement(Schema):
    _repr_fields = ['stage', 'total_time', 'pressure', ]
    time_remaining = Column(Float, nullable=False)
    total_time = Column(Float, nullable=False)
    pressure = Column(Float, nullable=False)
    stage = Column(Enum(LeakTestStage), default=LeakTestStage.VENT)


class HipotTesterMeasurement(Schema):
    _repr_fields = ['test_status', 'step', 'current', 'total_time', ]
    test_status = Column(String(16), nullable=False)
    step = Column(String(16), nullable=False)
    voltage = Column(Float, nullable=False)
    current = Column(Float, nullable=False)
    time_elapsed = Column(Float, nullable=False)
    total_time = Column(Float, nullable=False)
