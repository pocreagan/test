"""
performs instrument_setup on declarative_base factory
declares mixin class that handles repr, time created, and primary key id: int
Make contains convenience relationship instantiating to be used in schema.py
"""

import datetime
from dataclasses import dataclass
from typing import *

import sqlalchemy as sa
from sqlalchemy import Table
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.ext.declarative import DeclarativeMeta
from sqlalchemy.orm import relationship
from sqlalchemy.orm.relationships import RelationshipProperty

__all__ = [
    'declarative_base_factory',
    'TableMixin',
    'Relationship',
]


def metadata_kwargs() -> Dict[str, Dict[str, str]]:
    """
    builds naming convention for indices, constraints, and keys
    """
    # ? https://docs.sqlalchemy.org/en/13/core/metadata.html#sqlalchemy.schema.MetaData.params.info
    named_keys = {'col_0_label': '__%(column_0_label)s',
                  'col_0': '__%(column_0_name)s',
                  'table': '__%(table_name)s',
                  'referred_table': '__%(referred_table_name)s',
                  'constraint': '__%(constraint_name)s', }
    named_items = {'ix': '{col_0_label}',
                   'uq': '{table}{col_0}',
                   'ck': '{table}{col_0}',
                   'fk': '{table}{col_0}{referred_table}',
                   'pk': '{table}', }
    return {'naming_convention': {k: f'{k}{v.format(**named_keys)}' for k, v in named_items.items()}}


metadata = metadata_kwargs()


def declarative_base_factory(name: str) -> DeclarativeMeta:
    r = declarative_base(metadata=sa.MetaData(**metadata), cls=TableMixin, name=f'{name}_schema')
    r.connection_name = name
    return r


class TableMixin:
    """
    all tables have id and created_at columns
    also specifies __repr__ for instrument_debug print
    models should inherit from (Base, TableMixin)
    """
    __abstract__ = True

    # ? https://docs.sqlalchemy.org/en/13/orm/extensions/declarative/mixins.html

    @classmethod
    def id_fk(cls) -> sa.Column:
        return sa.Column(sa.Integer, sa.ForeignKey(cls.__name__ + '.id'))

    @declared_attr
    def __tablename__(self) -> str:
        return self.__name__

    id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    created_at = sa.Column(sa.DateTime, server_default=sa.func.now())

    __table__ = None
    _repr_fields: Optional[List[str]] = None

    def _format_one(self, k: str):
        v = getattr(self, k, None)
        if isinstance(v, datetime.datetime):
            return v.strftime(r'%Y%m%d:%H%M%S')
        return repr(v)

    def _repr(self, fields: List[str] = None) -> str:
        fields_ = fields if fields else type(self).__table__.c.keys()  # type: ignore
        s = ', '.join([f'{k}={self._format_one(k)}' for k in fields_])
        return f'{type(self).__name__}({s})'

    def __str__(self) -> str:
        return self._repr()

    def __repr__(self) -> str:
        if self._repr_fields is None:
            return super().__repr__()
        return self._repr(self._repr_fields)


class Relationship:
    # ? https://docs.sqlalchemy.org/en/13/orm/relationship_api.html?highlight=lazy
    @dataclass
    class _TwoWayRelationship:
        parent: RelationshipProperty
        child: RelationshipProperty

    @staticmethod
    def one_to_many(parent_table, parent_col, child_table, child_col) -> _TwoWayRelationship:
        """
        makes both ends of a one-to-many relationship
        the foreign order_key still needs to be specified on the child table first
        """
        # noinspection PyCallByClass
        return Relationship._TwoWayRelationship(
            parent=relationship(child_table, back_populates=child_col, lazy='select',
                                cascade='all, delete-orphan', single_parent=True),
            child=relationship(parent_table, back_populates=parent_col, lazy='select')
        )

    @staticmethod
    def one_to_one(parent_table, parent_col, child_table, child_col) -> _TwoWayRelationship:
        """
        makes both ends of a one-to-one relationship
        the foreign order_key still needs to be specified on the child table first
        """
        # noinspection PyCallByClass
        return Relationship._TwoWayRelationship(
            parent=relationship(child_table, back_populates=child_col, uselist=False, lazy='select',
                                cascade='all, delete-orphan', single_parent=True),
            child=relationship(parent_table, back_populates=parent_col, lazy='select')
        )

    @staticmethod
    def association(schema: DeclarativeMeta,
                    first_t: str, first_c: str, second_t: str, second_c: str) -> _TwoWayRelationship:
        table = sa.Table(
            f'association_{first_t}_{second_t}', schema.metadata,
            sa.Column(f'{first_t}_id', sa.Integer, sa.ForeignKey(f'{first_t}.id')),
            sa.Column(f'{second_t}_id', sa.Integer, sa.ForeignKey(f'{second_t}.id'))
        )
        return Relationship._TwoWayRelationship(
            parent=relationship(second_t, secondary=table, back_populates=second_c),
            child=relationship(first_t, secondary=table, back_populates=first_c),
        )

    @staticmethod
    def child_to_parent(other):
        """
        use only when left outer join is not needed
        use when lazy loading is acceptable
        """
        return relationship(other, lazy='select', innerjoin=True)

    @staticmethod
    def last_modified():
        return sa.Column(sa.DateTime, onupdate=sa.func.now())
