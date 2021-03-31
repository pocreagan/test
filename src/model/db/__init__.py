from functools import partial
from typing import Type

from typing_extensions import Protocol

from src.base import db
from src.base.db.connection import SessionManager
from src.base.log import logger
from src.model.db.schema import Schema

__all__ = [
    'connect',
]


class ConnectFunction(Protocol):
    def __call__(self, echo_sql: bool = False,
                 drop_tables: bool = False,
                 time_session: bool = False) -> Type[SessionManager]: ...


# noinspection PyTypeChecker
connect: ConnectFunction = partial(db.connect, conn_string="sqlite:///C:/Projects/instruments/dev/db/main.db",
                                   logger=logger, schema=Schema)
