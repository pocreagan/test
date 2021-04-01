import json
import subprocess
from collections import defaultdict
from dataclasses import InitVar
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from glob import glob
from itertools import starmap
from pathlib import Path
from typing import DefaultDict
from typing import Dict
from typing import List
from typing import Set
from typing import Tuple
from typing import Type
from typing import TypeVar
from typing import cast

import pandas as pd
import yaml as yml
from sqlalchemy import Table
from sqlalchemy import func

from src.base.db.connection import SessionType
from src.base.log import logger
from src.model.db import connect
from src.model.db import schema
from src.model.db.schema import AppConfigUpdate
from src.model.db.schema import ConfigFile
from src.model.db.schema import EEPROMConfig
from src.model.db.schema import EEPROMRegister
from src.model.db.schema import LightingStation3Param
from src.model.db.schema import LightingStation3ParamRow
from src.model.db.schema import YamlFile

log = logger(__name__)

_anchor = Path(r'//wet-pdm/Common/Test Data Backup/test/versioned')


@dataclass
class _Path:
    fp: InitVar[str]
    filepath: Path = field(repr=False, default=None)
    path_key: str = None
    last_modified: datetime = None

    def __post_init__(self, fp: str):
        self.filepath = Path(fp)
        self.path_key = str(self.filepath.relative_to(_anchor))
        self.last_modified = datetime.fromtimestamp(self.filepath.stat().st_mtime)


def _find_files(ext: str) -> Dict[str, _Path]:
    return {fp.path_key: fp for fp in list(map(_Path, glob(
        str(_anchor / '**' / f'*{ext}'), recursive=True
    )))}


class ConfigError(Exception):
    pass


_T = TypeVar('_T')


class ConfigUpdate:
    kwargs = dict(
        # echo_sql=True,
        # drop_tables=True,
    )
    params_objects = ((r'lighting/station3/params.xlsx', LightingStation3Param, LightingStation3ParamRow),)
    new: int
    session: SessionType
    rev: int
    app_config_obj: AppConfigUpdate
    object_id_dict: DefaultDict[str, Set[int]]

    def __init__(self):
        if not _anchor.exists():
            raise FileNotFoundError(f'cannot access config files in {_anchor}')
        self.session_manager = connect(**self.kwargs)

    def test(self) -> None:
        with self.session_manager() as session:
            print(EEPROMConfig.get(session, '938 ArenaPar WRMA', False))

    def update(self) -> None:
        if subprocess.check_output("git diff --quiet || echo 'dirty'", shell=True).decode().strip() != '':
            raise ConfigError('working tree must be clean to perform config update.')

        self.new = 0
        self.object_id_dict = defaultdict(set)
        with self.session_manager() as session:
            self.session = session
            self.app_config_obj = self.session.make(AppConfigUpdate(commit=subprocess.run(
                ['git', 'rev-parse', '--verify', 'HEAD'], capture_output=True, text=True
            ).stdout))
            self.rev = self.app_config_obj.id
            self.handle_eeprom_xlsx()
            list(starmap(self.handle_params_xlsx, self.params_objects))
            self.handle_yml()
            self.app_config_obj.objects = json.dumps(
                {k: list(v) for k, v in self.object_id_dict.items()}
            )
            if not self.new:
                session.rollback()

    def make_roster(self, extension: str) -> List[_Path]:
        sub_q = self.session.query(
            func.max(ConfigFile.last_modified), ConfigFile.fp, ConfigFile.id
        ).group_by(ConfigFile.fp).subquery()
        extant_files = {
            record.fp: record for record in self.session.query(
                ConfigFile).join(sub_q, ConfigFile.id == sub_q.c.id).all()
        }
        new_files, reusable = [], []
        deprecated = set()
        for k, v in _find_files(extension).items():
            extant = extant_files.get(k, None)
            if extant is None or extant.last_modified < v.last_modified:
                new_files.append(v)
            elif extant is not None:
                log.debug(f'reusing -> {k}')
                for obj_name, obj_id in json.loads(extant.children):
                    obj = self.session.query(getattr(schema, obj_name)).get(obj_id)
                    obj.rev = self.rev
                    self.add_to_app_update(obj)
            else:
                deprecated.add(k)
        [log.info(f'deprecated -> {k}') for k in deprecated]
        return new_files

    def _make_file_record(self, new: _Path, previous_new_count: int, parents: List[Table]) -> None:
        if previous_new_count != self.new:
            self.make_file_record(new, parents)

    def add_to_app_update(self, obj) -> None:
        self.object_id_dict[type(obj).__qualname__].add(obj.id)

    def make_file_record(self, new: _Path, parents: List[Table]) -> None:
        self.session.make(ConfigFile(
            fp=new.path_key, last_modified=new.last_modified,
            children=json.dumps([(type(p).__name__, p.id) for p in parents])
        ))
        log.info(f'merged   -> {new.path_key}<{new.last_modified}>')

    def handle_yml(self) -> None:
        for new in self.make_roster('.yml'):
            log.debug(f'checking -> {new.path_key}')
            try:
                with open(new.filepath) as y:
                    content = json.dumps(yml.load(y, Loader=yml.FullLoader))
            except yml.YAMLError as e:
                raise ValueError(f'failed to confirm {new.filepath}') from e

            obj = self.session.query(YamlFile).filter(
                YamlFile.fp == new.path_key, YamlFile.content == content
            ).one_or_none()
            if obj is None:
                obj = self.session.make(YamlFile(content=content, fp=new.path_key, rev=self.rev))
            else:
                obj.rev = self.rev

            self.new += 1
            self.make_file_record(new, [obj])
            self.add_to_app_update(obj)

    @staticmethod
    def _parse_spreadsheet(new: _Path, **kwargs) -> pd.DataFrame:
        log.debug(f'checking -> {new.path_key}')
        try:
            return pd.read_excel(new.filepath, comment='#', sheet_name=None, **kwargs)
        except PermissionError as e:
            raise ValueError(f'failed to read {new.path_key}') from e

    @staticmethod
    def _sheet_setup(new: _Path, name: str, sheet: pd.DataFrame) -> Tuple[List, List[Dict]]:
        log.debug(f'checking -> {new.path_key}::{name}')
        records = cast(List[Dict], sheet.to_dict('records'))
        if not records:
            raise ValueError(f'{new.path_key} -> {name} empty')
        return [], records

    def _make_children(self, children: List, child_cla, records: List[Dict]) -> None:
        for record in records:
            existing_reg = self.session.query(child_cla).filter_by(**record).one_or_none()
            if existing_reg is None:
                children.append(self.session.make(child_cla(**record)))
            else:
                children.append(existing_reg)

    _T2 = TypeVar('_T2')

    def _make_parent(self, parent_cla: Type[_T2], children: List, kwargs: Dict, merge_msg: str,
                     child_field: str) -> _T2:
        parent = self.session.query(parent_cla).filter_by(**kwargs).first()
        if parent is None or getattr(parent, child_field) != children:
            parent = self.session.make(parent_cla(rev=self.rev, **kwargs))
            setattr(parent, child_field, children)
            log.info(merge_msg)
            self.new += 1

        self.add_to_app_update(parent)
        return parent

    @staticmethod
    def validate_eeprom_records(records: List[Dict], file_s: str) -> None:
        _reg_set = set()
        for i, register in enumerate(records):
            tup = tuple(register.values())
            if tup in _reg_set:
                raise ValueError(f'{file_s} line{i} duplicated')
            _reg_set.add(tup)

            if register['target'] not in {5, 7, 8}:
                raise ValueError(f'{file_s} line{i} bad target')
            if not 0 <= register['index'] < 256:
                raise ValueError(f'{file_s} line{i} bad index')
            if not 0 <= register['value'] < 2 ** 32:
                raise ValueError(f'{file_s} line{i} bad value')

    def handle_eeprom_xlsx(self) -> None:
        for new in self.make_roster('eeprom.xlsx'):
            _previous_new_count, parents = self.new, []

            ds = self._parse_spreadsheet(new, names=['target', 'index', 'value'], header=None)
            for name, sheet in ds.items():  # type:str, pd.DataFrame
                children, records = self._sheet_setup(new, name, sheet)

                self.validate_eeprom_records(records, f'{new.path_key} -> {name}')

                self._make_children(children, EEPROMRegister, records)
                parents.append(self._make_parent(EEPROMConfig, children, dict(
                    is_initial='initial.eeprom.xlsx' in str(new.filepath), name=name
                ), f'merged   -> {new.path_key}::{name}<{new.last_modified}>', 'registers'))

            self._make_file_record(new, _previous_new_count, parents)

    def handle_params_xlsx(self, extension: str, param_model, row_model, validator=None) -> None:
        for new in self.make_roster(extension):
            _previous_new_count, parents = self.new, []

            ds = self._parse_spreadsheet(new)
            for name, sheet in ds.items():  # type:str, pd.DataFrame
                children, records = self._sheet_setup(new, name, sheet)

                if callable(validator):
                    validator(records, f'{new.path_key} -> {name}')

                self._make_children(children, row_model, [
                    dict(row_num=row_num, **row) for row_num, row in enumerate(records)
                ])
                parents.append(
                    self._make_parent(param_model, children, dict(name=name),
                                      f'merged   -> {new.path_key}::{name}<{new.last_modified}>', 'rows'))

            self._make_file_record(new, _previous_new_count, parents)


if __name__ == '__main__':
    with logger:
        updater = ConfigUpdate()
        updater.update()
        updater.test()
