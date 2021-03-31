"""
declarative models should inherit from (meta.Base, meta.TableMixin)
default factories should be declared in helper.py
"""
import json
import re
import traceback
from operator import attrgetter
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union

from sqlalchemy import Column
from sqlalchemy import func
from sqlalchemy import UniqueConstraint
from sqlalchemy.ext.declarative import DeclarativeMeta
from sqlalchemy.sql.sqltypes import Boolean
from sqlalchemy.sql.sqltypes import DateTime
from sqlalchemy.sql.sqltypes import Enum
from sqlalchemy.sql.sqltypes import Float
from sqlalchemy.sql.sqltypes import Integer
from sqlalchemy.sql.sqltypes import LargeBinary
from sqlalchemy.sql.sqltypes import String
from sqlalchemy.sql.sqltypes import Text
from typing_extensions import Protocol

from src.base.actor.configuration import get_configs_on_object
from src.base.db.connection import SessionType
from src.base.db.meta import *
from src.model.db.helper import *
from src.model.enums import *

__all__ = [
    'Schema',
    'AppConfigUpdate',
    'ConfigFile',
    'PartNumber',
    'Device',
    'Station',
    'TestStep',
    'FirmwareVersion',
    'FirmwareCode',
    'FirmwareIteration',
    'LightingStation1ResultRow',
    'YamlFile',
    'EEPROMConfig',
    'EEPROMRegister',
    'EEPROMConfigIteration',
    'LightingStation3Param',
    'LightingStation3ParamRow',
    'LightingStation3LightMeasurement',
    'LightingStation3ResultRow',
    'TestStepProtocol',
    'TestIterationProtocol',
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
    version_to_code = Relationship.one_to_one('FirmwareVersion', 'code', 'FirmwareCode', 'version')


Schema: Union[DeclarativeMeta, TableMixin] = declarative_base_factory('main')


class AppConfigUpdate(Schema):
    _repr_fields = ['created_at']
    objects = Column(Text)


class ConfigFile(Schema):
    _repr_fields = ['fp', 'last_modified']
    fp = Column(String(256), nullable=False)
    last_modified = Column(DateTime, nullable=False)
    children = Column(Text)


class YamlFile(Schema):
    _repr_fields = ['fp', 'created_at']
    rev = Column(Integer, nullable=False)
    fp = Column(String(256), nullable=False)
    content = Column(Text, nullable=False)

    @classmethod
    def get(cls, session: SessionType, fp: str) -> 'YamlFile':
        result: Optional[YamlFile] = session.query(cls).filter(
            cls.fp == fp, cls.rev == session.query(func.max(AppConfigUpdate.id)).subquery()
        ).one_or_none()
        if not result:
            raise ValueError(f'{fp} deprecated or not present in the {cls.__name__} table')
        return json.loads(result.content)

    @classmethod
    def update_object(cls, session: SessionType, obj) -> None:
        [_c.update_from(cls.get(session, _c.fp)) for _c in get_configs_on_object(obj)]


lighting_station3_rows_association_table = Relationship.association(
    Schema, 'LightingStation3Param', 'rows', 'LightingStation3ParamRow', 'params',
)


class LightingStation3Param(Schema):
    _repr_fields = ['name']
    rev = Column(Integer, nullable=False)
    name = Column(String(128), nullable=False)
    rows = lighting_station3_rows_association_table.parent

    @classmethod
    def get(cls, session: SessionType, name: str) -> List['LightingStation3ParamRow']:
        result = session.query(cls).filter(
            cls.name == name, cls.rev == session.query(func.max(AppConfigUpdate.id)).subquery()
        ).one_or_none()
        if not result:
            raise ValueError(f'{name} deprecated or not present in the {cls.__name__} table')
        return list(sorted(result.rows, key=attrgetter('row_num')))


class LightingStation3ParamRow(Schema):
    _repr_fields = ['x_nom', 'y_nom', 'color_dist_max', 'fcd_nom',
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
        return {ch: getattr(self, f'dmx_ch{ch}') for ch in range(1, 11)}


light_measurement_association_table = Relationship.association(
    Schema, 'LightingStation3ResultRow', 'light_measurements',
    'LightingStation3LightMeasurement', 'result_rows'
)


class LightingStation3ResultRow(Schema):
    _repr_fields = ['x', 'y', 'fcd', 'p', 'pct_drop', ]
    param_row_id = LightingStation3ParamRow.id_fk()
    param_row = Relationship.child_to_parent(LightingStation3ParamRow)
    light_measurements = light_measurement_association_table.parent
    t = Column(DateTime, nullable=False)
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)
    fcd = Column(Float, nullable=False)
    cct = Column(Float, nullable=False)
    duv = Column(Float, nullable=False)
    p = Column(Float, nullable=False)
    pct_drop = Column(Float, nullable=False)
    cie_dist = Column(Float)
    cie_pf = Column(Boolean, default=False)
    fcd_pf = Column(Boolean, default=False)
    p_pf = Column(Boolean, default=False)
    pct_drop_pf = Column(Boolean, default=False)

    def pf(self) -> bool:
        return self.cie_pf and self.fcd_pf and self.p_pf and self.pct_drop_pf


class LightingStation3LightMeasurement(Schema):
    _repr_fields = ['x', 'y', 'fcd', 'cct', 'duv', ]
    result_row_id = LightingStation3ResultRow.id_fk()
    result_rows = light_measurement_association_table.child
    t = Column(DateTime, nullable=False)
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)
    fcd = Column(Float, nullable=False)
    cct = Column(Float, nullable=False)
    duv = Column(Float, nullable=False)


register_association_table = Relationship.association(
    Schema, 'EEPROMConfig', 'registers', 'EEPROMRegister', 'configs'
)


class EEPROMConfig(Schema):
    rev = Column(Integer, nullable=False)
    is_initial = Column(Boolean)
    name = Column(String(128), nullable=False)
    registers: Any = register_association_table.parent

    @classmethod
    def get(cls, session: SessionType, name: str, is_initial: bool) -> Dict[Tuple[int, int], int]:
        result = session.query(cls).filter(
            cls.name == name, cls.is_initial == is_initial, cls.rev == session.query(
                func.max(AppConfigUpdate.id)
            ).subquery()
        ).one_or_none()
        if not result:
            raise ValueError(
                f'{name} <initial={is_initial}> deprecated or not present in the {cls.__name__} table'
            )
        return {(reg.target, reg.index): reg.value for reg in result.registers}


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
    config_iterations = Rel.device_to_config_iterations.parent
    firmware_iterations = Rel.device_to_firmware_iterations.parent
    # test_iterations = Rel.device_to_test_iterations.parent
    test_step_iterations = Rel.device_to_test_step_iterations.parent
    # release = Rel.device_to_released_device.parent


class Station(Schema):
    _repr_fields = ['name', ]
    pc_name = Column(String(128), nullable=False, unique=True)
    name = Column(String(64), unique=True, nullable=False)


class TestStepProtocol(Protocol):
    p_f: bool
    error: str

    def exception(self) -> None:
        """
        only call this method in an except: clause
        """
        self.p_f = False
        self.error = traceback.format_exc()


class TestIterationProtocol(Protocol):
    dut_id: int
    p_f: bool
    steps: List[int]


class TestStep(Schema):
    _repr_fields = ['name', 'success', 'reason']
    name = Column(String(128), nullable=False)
    p_f = Column(Boolean)
    error = Column(Text)
    # iterations = Rel.stage_to_iterations.parent


class FirmwareVersion(Schema):
    _repr_fields = ['pn', 'version', ]
    fp_to_fields_re = re.compile(r'(?i)\\80-(\d+)_\D+(\d+)\.dta')

    pn = Column(Integer, nullable=False)
    version = Column(Integer, nullable=False)
    code = Rel.version_to_code.parent

    __table_args__ = (
        UniqueConstraint('pn', 'version'),
    )

    @classmethod
    def make_from(cls, fp: Path) -> 'FirmwareVersion':
        pn, version = cls.fp_to_fields_re.findall(str(fp))[0]
        return FirmwareVersion(pn=int(pn), version=int(version), code=FirmwareCode.get_from(fp))


class FirmwareCode(Schema):
    _repr_fields = ['hash', ]
    fw_id = FirmwareVersion.id_fk()
    code = Column(LargeBinary, nullable=False)
    hashed = Column(String(32), default=make_hash_f, onupdate=make_hash_f, unique=True)
    version = Rel.version_to_code.child

    @classmethod
    def get_from(cls, fp: Path) -> 'FirmwareCode':
        with open(fp, 'rb') as dat:
            return FirmwareCode(code=dat.read())


class EEPROMConfigIteration(Schema):
    _repr_fields = ['dut', 'config', 'created_at', ]
    dut_id = Device.id_fk()
    station_id = Station.id_fk()
    config_id = EEPROMConfig.id_fk()
    dut = Rel.device_to_config_iterations.child
    config = Relationship.child_to_parent(EEPROMConfig)


class FirmwareIteration(Schema):
    _repr_fields = ['dut', 'fw', 'created_at', ]
    dut_id = Device.id_fk()
    station_id = Station.id_fk()
    firmware_id = FirmwareVersion.id_fk()
    dut = Rel.device_to_firmware_iterations.child
    fw = Relationship.child_to_parent(FirmwareVersion)


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
