"""
declarative base class must be imported in order:
    meta -> schema -> connection
session manager is defined with Session in closure and
should be imported from here but not used here
"""

from contextlib import contextmanager
from time import perf_counter
from typing import Callable, Type, ContextManager
from typing import TypeVar

import sqlalchemy as sa
from sqlalchemy.ext.declarative import DeclarativeMeta
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.session import Session
from typing_extensions import Protocol

__all__ = [
    'connect',
    'SessionManager',
    'SessionType',
]

_T = TypeVar('_T')


class SessionType(Session):
    def make(self: Session, obj: _T) -> _T:
        self.add(obj)
        self.flush([obj])
        return obj

    def context_commit(self) -> None:
        super().commit()

    def commit(self):
        raise Exception('must not explicitly invoke .commit()')


SessionManager = Callable[..., ContextManager[SessionType]]

def connect(logger, schema: DeclarativeMeta, conn_string: str = '',
            echo_sql: bool = False,
            drop_tables: bool = False, **kwargs) -> SessionManager:
    """
    sets up the sqlalchemy connection and declares a transaction factory context manager
    """
    _ = kwargs

    log = logger(__name__)

    # SUPPRESS-LINTER <attr added to subclass in meta.py>
    # noinspection PyUnresolvedReferences
    _connection = schema.connection_name

    engine = sa.create_engine(conn_string, echo=echo_sql)
    log.info(f'connected to database: {conn_string}')

    session_constructor: Callable[[], SessionType] = sessionmaker(bind=engine, class_=SessionType)
    log.debug(f'built session constructor: {conn_string}')

    if drop_tables:

        # noinspection PyUnresolvedReferences
        schema.metadata.drop_all(engine)
        log.warning(f'dropped {_connection} tables')

    # noinspection PyUnresolvedReferences
    schema.metadata.create_all(engine)
    log.info(f'mapped {_connection} schema')

    @contextmanager
    def session_manager_f(expire: bool = True) -> ContextManager[SessionType]:
        """
        provide a transactional scope around a series of operations
        """
        # ? https://docs.sqlalchemy.org/en/13/orm/session_basics.html

        session = session_constructor()
        session.expire_on_commit = expire

        try:
            yield session

        except Exception as e:
            session.rollback()
            raise e

        else:
            session.context_commit()

        finally:
            session.close()

    return session_manager_f
