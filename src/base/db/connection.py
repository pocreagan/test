"""
declarative base class must be imported in order:
    meta -> schema -> connection
session manager is defined with Session in closure and
should be imported from here but not used here
"""

from contextlib import contextmanager
from time import perf_counter
from typing import Callable
from typing import TypeVar

import sqlalchemy as sa
from sqlalchemy.ext.declarative.api import DeclarativeMeta
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm.session import Session
from typing_extensions import Protocol

__all__ = [
    'connect',
    'SessionManager',
    'SessionType',
]


class SessionManager(Protocol):
    def __init__(self, expire_on_commit: bool = True) -> None: ...

    def __enter__(self) -> 'SessionType': ...


def _raise_if_commit(*args, **kwargs) -> None:
    raise Exception('must not explicitly invoke .commit()')


_T = TypeVar('_T')


class SessionType(Session):
    def make(self, obj: _T) -> _T: ...


def make(session: Session, obj: _T) -> _T:
    session.add(obj)
    session.flush([obj])
    return obj


def connect(logger, schema: DeclarativeMeta, conn_string: str = '',
            time_session: bool = False,
            echo_sql: bool = False,
            drop_tables: bool = False, **kwargs) -> Callable[[], SessionManager]:
    """
    sets up the sqlalchemy connection and declares a transaction factory context manager
    """
    _ = kwargs

    log = logger(__name__)
    log.debug(f'building {conn_string} session manager')

    # SUPPRESS-LINTER <attr added to subclass in meta.py>
    # noinspection PyUnresolvedReferences
    connection = schema.connection_name

    engine = sa.create_engine(conn_string, echo=echo_sql)
    log.info(f'connected to {conn_string} db')

    session_constructor = sessionmaker(bind=engine)

    if drop_tables:

        schema.metadata.drop_all(engine)
        log.warning(f'dropped {connection} tables')

    schema.metadata.create_all(engine)
    log.info(f'mapped {connection} schema')

    @contextmanager
    def session_manager_f(expire_on_commit: bool = True):
        """
        provide a transactional scope around a series of operations
        """
        # ? https://docs.sqlalchemy.org/en/13/orm/session_basics.html

        ti = perf_counter()
        session = session_constructor()
        session.expire_on_commit = expire_on_commit
        _commit, session.commit = session.commit, _raise_if_commit
        session.make = make.__get__(session, Session)

        try:
            yield session

        except Exception as e:
            session.rollback()
            raise e

        else:
            _commit()

        finally:
            session.close()
            if time_session:
                te = round((perf_counter() - ti) * 1000, 1)
                log.debug(f'$SESSION-TIME: {te}MS ({connection})')

    return session_manager_f
