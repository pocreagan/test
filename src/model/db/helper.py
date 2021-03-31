import hashlib
from dataclasses import dataclass
from dataclasses import fields
from typing import TypeVar
from urllib.parse import quote_plus

from typing import Type
from sqlalchemy import Table
from sqlalchemy.engine.default import DefaultExecutionContext

__all__ = [
    'make_hash',
    'make_hash_f',
    'password',
    'dataclass_to_model',
]


def password(s: str) -> str:
    return quote_plus(s)


def make_hash(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def make_hash_f(context: DefaultExecutionContext) -> str:
    return make_hash(context.get_current_parameters()['code'])


_T = TypeVar('_T', bound=Table)


def dataclass_to_model(dc: dataclass, model: Type[_T], **kwargs) -> _T:
    return model(**{k.name: getattr(dc, k.name) for k in fields(dc)}, **kwargs)
