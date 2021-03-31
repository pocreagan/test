"""
declarative models should inherit from (meta.Base, meta.TableMixin)
default factories should be declared in helper.py
"""

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import Integer
from sqlalchemy import String

from src.base.general import dict_from
from src.base.db.meta import *

__all__ = [
    'Schema',
    'Log',
    'LogRecord',
]


Schema = declarative_base_factory('logging')


class Rel:
    session_to_log_records = Relationship.one_to_many('Log', 'records', 'LogRecord', 'session')


class Log(Schema):
    _repr_fields = ['pc_name', 'name', 'session']
    _keys = ['last_commit', 'build_id', 'build_type', 'v']
    session = Column(Integer, autoincrement=True)
    hostname = Column(String(128), nullable=False)
    human_readable = Column(String(64), nullable=False)
    last_commit = Column(String(40), nullable=False)
    build_id = Column(Integer, nullable=False)
    build_type = Column(String(32), nullable=False)
    v = Column(String(16), nullable=False)
    records = Rel.session_to_log_records.parent

    @classmethod
    def from_ini(cls, station, build) -> 'Log':
        return cls(hostname=station.hostname, human_readable=station.human_readable,
                   **{k: build[k] for k in cls._keys})


class LogRecord(Schema):
    _repr_fields = ['created', 'levelname', 'name', 'message', ]
    _keys = ['levelno', 'levelname', 'name', 'lineno', 'created_dt', 'msg', 'processName']
    levelno = Column(Integer, nullable=False)
    processName = Column(String(16), nullable=False)
    levelname = Column(String(8), nullable=False)
    name = Column(String(256), nullable=False)
    lineno = Column(Integer, nullable=False)
    created_dt = Column(DateTime, nullable=False)
    msg = Column(String(512), nullable=False)
    session_id = Log.id_fk()
    session = Rel.session_to_log_records.child

    @classmethod
    def from_record(cls, record, session_id: int = None) -> 'LogRecord':
        return LogRecord(**dict_from(record, cls._keys), session_id=session_id)
