import collections
import datetime
import logging.handlers
import queue
import threading
import time
from functools import lru_cache
from logging import Formatter as LFormatter
from typing import *  # type: ignore

__all__ = [
    'Handler',
    'Formatter',
    'make_handler',
    'QueueListener'
]

CT = 'relative_created_ms'
CAT = 'abbreviated_name:<25'
MOD = 'name:<60'
PROC = 'processName:<4'
LEVEL = 'levelname:<7'


class Formatter:
    class Base(LFormatter):
        _format_s: str

        _path_to_abbreviation = {
            'app.model.resources': 'RESOURCE',
            'app.base.db.connection': 'DATABASE',
            'app': 'MAIN',
            'app.window': 'VIEW',
            'app.LL2.controller': 'CONTROLLER',
        }
        _replace_by_prefix = {
            'app.base.': 'LOGGING',
            'app.controller.rs485.': 'RS485',
        }
        _replace_prefix = {
            'app.view': 'VIEW',
        }
        _replace_portion = {
            'app.controller.equipment.',
        }
        _process_map = {
            'MainProcess': 'MAIN',
            'Controller': 'CONT'
        }

        def _make_relative_time(self, _created_t: float) -> str:
            if not self.start_time:
                self.start_time = _created_t
            return str(round((_created_t - self.start_time) * 1000) % 60000).zfill(5)

        @staticmethod
        def _make_dt(_dt: datetime.datetime) -> Tuple[str, str]:
            dt = _dt.strftime('%Y%m%d%H%M%S.%f')[:-3]
            return dt[:8], dt[8:]

        @lru_cache(maxsize=256)
        def _make_abbreviated_name(self, _name: str) -> str:
            name = self._path_to_abbreviation.get(_name, None)
            if name:
                return name
            for k, v in self._replace_by_prefix.items():
                if _name.startswith(k):
                    return v
            for k, v in self._replace_prefix.items():
                if _name.startswith(k):
                    return v + _name.removeprefix(k).upper()
            for k in self._replace_portion:
                if _name.startswith(k):
                    return _name.removeprefix(k).upper()
            return _name

        def _add_stack_info(self, record: logging.LogRecord, s: str) -> str:
            if record.exc_info:
                if not record.exc_text:
                    record.exc_text = self.formatException(record.exc_info)
            for string in (record.exc_text, record.exc_info):
                if string:
                    if s[-1:] != "\n":
                        s = s + "\n"
                    s = s + string
            return s

        def format(self, record: logging.LogRecord) -> str:
            # SUPPRESS-LINTER <added created_dt in QueueProducer>
            # noinspection PyUnresolvedReferences
            record.unformatted = record.msg
            record.created_dt = datetime.datetime.fromtimestamp(record.created)
            p = record.processName
            record.processName = self._process_map.get(p, p)

            record.date_s, record.time_s = self._make_dt(record.created_dt)
            record.relative_created_ms = self._make_relative_time(record.created)
            record.abbreviated_name = self._make_abbreviated_name(record.name)
            record.formatted = s = self._add_stack_info(record, self._format_s.format(**vars(record)))
            return s

        # SUPPRESS-LINTER <the stuff in super().__init__ is a waste of time>
        # noinspection PyMissingConstructor
        def __init__(self):
            self.start_time = None

    class Console(Base):
        _format_s = f'[ {{{CT}}} ] [ {{{LEVEL}}} ] [ {{{PROC}}} ] [ {{{CAT}}} ]  {{msg}}'

    class FullConsole(Base):
        _format_s = f'{{date_s}}{{time_s}} - {{{LEVEL}}} - {{{PROC}}} - {{{MOD}}} - {{msg}}'

    class ForTSV(Base):
        _format_s = f'{{date_s}}{{time_s}}\t{{{LEVEL}}}\t{{{PROC}}}\t{{{MOD}}}\t{{msg}}'


class Handler:
    class QueuePassThrough(logging.handlers.QueueHandler):
        pass

    class LoaderQueue(logging.handlers.QueueHandler):
        def __init__(self, q: queue.Queue) -> None:
            self._lock = threading.Lock()
            self.do = True
            super().__init__(q)

        def emit(self, record: logging.LogRecord) -> None:
            if self.do:
                with self._lock:
                    # noinspection PyBroadException
                    try:
                        # noinspection PyUnresolvedReferences
                        self.queue.put_nowait(record.msg)
                    except Exception:
                        self.handleError(record)

        def stop(self) -> None:
            with self._lock:
                self.do = False

    class Deque(logging.Handler):
        def __init__(self, d: collections.deque):
            self.d = d
            self.new = False
            super().__init__()

        def get(self) -> List[str]:
            self.acquire()
            try:
                _lines = list(self.d)
                self.d.clear()
                self.new = False
                return _lines
            finally:
                self.release()

        def emit(self, record: logging.LogRecord) -> None:
            # noinspection PyUnresolvedReferences
            self.d.append(record.msg)
            self.new = True

    class FormatHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            self.format(record)

    class Database(logging.Handler):
        _cache_size: int = 0
        _manual_flush_message = '$log_stop$'

        def force_emit(self, message: str) -> bool:
            return message == self._manual_flush_message

        def force_not_emit(self, message: str) -> bool:
            _ = self
            return 'SESSION TIME' in message

        def __init__(self, app, connect_function: Callable, logger):
            from src.base.log import schema
            cache_config = app.DATABASE.logging
            db = app.DATABASE.connections['logging']
            self._cache_flush_threshold: int = cache_config['cache_size']
            self._cache_max_time_s: float = cache_config['cache_max_time_s']
            self._session_manager = connect_function(logger, schema.Schema, **db)
            self._log, self._log_record = schema.Log, schema.LogRecord

            with self._session_manager() as session:
                session.add(self._log.from_ini(app.STATION, app.BUILD))
                session.commit()

                # SUPPRESS-LINTER <this is definitely correct>
                # noinspection PyUnresolvedReferences
                self._id = session.__read(self._log).order_by(self._log.id.desc()).first().id

            self._records = collections.deque()
            self.clear_cache()
            self._get_t = time.time
            self._next_emit = self._get_t()

            super().__init__()

        @property
        def do_flush(self) -> bool:
            return (self._cache_size >= self._cache_flush_threshold) or (self._get_t() > self._next_emit)

        def make_next_emit(self) -> None:
            self._next_emit = time.time() + self._cache_max_time_s

        def flush_cache_to_db(self) -> None:
            with self._session_manager() as session:
                session.add_all(self._records)
            self.clear_cache()
            self.make_next_emit()

        def add_record_to_cache(self, record: logging.LogRecord) -> None:
            self._records.append(self._log_record.from_record(record, self._id))
            self._cache_size += 1

        def clear_cache(self) -> None:
            self._records.clear()
            self._cache_size = 0

        def emit(self, record: logging.LogRecord) -> None:
            self.add_record_to_cache(record)

            msg = record.msg
            if not self.force_not_emit(msg):
                if self.do_flush or self.force_emit(msg):
                    self.flush_cache_to_db()

    class Console(logging.StreamHandler):

        # noinspection PyUnresolvedReferences
        def format(self, record: logging.LogRecord) -> str:
            if record.formatted:
                return record.formatted
            return record.msg

    class Suppressed(logging.Handler):

        def emit(self, record: logging.LogRecord) -> None:
            pass


class QueueListener(logging.handlers.QueueListener):
    pass


def make_handler(handler, *formatters, log_level: int = None) -> logging.Handler:
    if log_level is not None:
        handler.setLevel(log_level)
    for _fmt in formatters or []:
        handler.setFormatter(_fmt())
    return handler
