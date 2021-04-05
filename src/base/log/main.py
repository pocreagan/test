import collections
import logging
import time
from multiprocessing import current_process
from multiprocessing import Queue
from typing import cast, Callable
from typing import Optional

from src.base import atexit_proxy as atexit
from src.base.general import chain
from src.base.log.objects import *

__all__ = [
    'logger',
]


class _Logger:
    """
    NORMAL USAGE:
        ex: log = logger(__name__)

    to set logger output, call .to_<destination> method
    """

    _root = 'app'
    _src_roots = {'base', 'model', 'controller', 'view'}
    _log_stop_sentinel: str = '$log_stop$'
    _listen_stop_wait: float = .1
    _listener: Optional[QueueListener] = None
    q: Optional[Queue] = None
    d: Optional[Handler.Deque] = None

    def __init__(self):
        self._has_been_started = False
        self._this_name = self._make_name(__name__)
        self._listener = None
        self.loader_queue_handler = None
        self._handlers, self._handler_names = list(), list()

    @staticmethod
    def _process_name() -> str:
        return current_process().name

    @staticmethod
    def _is_not_extant(name: str) -> bool:
        # noinspection PyUnresolvedReferences
        return name not in logging.root.manager.loggerDict  # type: ignore

    @classmethod
    def _make_name(cls, name: str) -> str:
        """
        transform __name__ to fall under application root logger_
        """
        name = name.replace('src.', '')
        for root in cls._src_roots:
            if name.startswith(root):
                name = name[len(root):]
                name = f'{cls._root}.{root}{name}'
                break
        else:
            # name = f'{cls._root}.{name}'
            pass
        return name.replace('__main__', cls._root)

    def _get_log(self, name: str) -> logging.Logger:
        """
        uses builtin getLogger to cascade process queue handler
        """
        name = self._make_name(name)
        if self._is_not_extant(name) and (name != self._this_name):
            self._get_log(self._this_name).debug(f'attached {name}')
        return logging.getLogger(name)

    def __call__(self, name: str) -> logging.Logger:
        """
        on first call, initialize the app root logger_
        make this process's logging stack and make the root logger_ emit to it
        """
        if self._is_not_extant(self._root):
            log = logging.getLogger(self._root)
            log.setLevel(logging.DEBUG)
            self.q = Queue()
            log.addHandler(make_handler(Handler.QueuePassThrough(self.q)))
            self._get_log(__name__).info('started enqueue handler')
            self._has_been_started = True
        return self._get_log(name)

    @property
    def level(self):
        return getattr(self, '_level', logging.DEBUG)

    @level.setter
    def level(self, value):
        logging.getLogger(self._root).setLevel(value)
        setattr(self, '_level', value)

    def stop(self):
        """
        sends sentinel to queue handler to flush all extant records
        then stops listener
        """
        if hasattr(self._listener, 'stop'):
            self._get_log(__name__).info(self._log_stop_sentinel)
            time.sleep(self._listen_stop_wait)
            try:
                self._listener.stop()

            except AttributeError:
                pass  # if the listener isn't running, no problem

        log = logging.getLogger(self._root)
        handlers = log.handlers
        [log.removeHandler(h) for h in handlers]

    @chain
    def _add_handler(self, handler):
        self._handler_names.append(handler.__class__.__name__.lower())
        self._handlers.append(handler)

    def format(self) -> '_Logger':
        return self._add_handler(make_handler(Handler.FormatHandler(), Formatter.Console))

    def to_db(self, app, connect_function, logger_instance) -> '_Logger':
        return self._add_handler(make_handler(Handler.Database(app, connect_function, logger_instance)))

    def to_console(self) -> '_Logger':
        return self._add_handler(make_handler(Handler.Console()))

    def to_deque(self) -> '_Logger':
        self.d = Handler.Deque(collections.deque(maxlen=5000))
        return self._add_handler(make_handler(self.d))

    def suppressed(self) -> '_Logger':
        return self._add_handler(make_handler(Handler.Suppressed()))

    def with_suppressed(self, f: Callable[[], None]) -> None:
        self.format().suppressed().start()
        try:
            f()
        finally:
            self.stop()

    def to_loader(self) -> 'Queue':
        _q = Queue()
        self.loader_queue_handler = Handler.LoaderQueue(_q)
        self._add_handler(make_handler(self.loader_queue_handler))
        return _q

    def kill_loader(self) -> None:
        self.loader_queue_handler.stop()

    def to_window(self, window) -> '_Logger':
        self.to_deque()
        window.log_deque = self.d
        return self

    def to_main_process(self, main_process_q: Queue) -> '_Logger':
        return self._add_handler(make_handler(Handler.QueuePassThrough(main_process_q)))

    @chain
    def start(self):
        """
        listens to main process logging stack queue and emits to database and console
        """
        log_s = f'dequeue to {self._handler_names}'
        if self._has_been_started and (self._listener is None):
            self._listener = QueueListener(cast(Queue, self.q), *self._handlers,
                                           respect_handler_level=True)  # type: ignore
            self._listener.start()
            self._get_log(__name__).info(f'started {log_s}')
        else:
            raise AttributeError(f'tried to init {log_s} without initializing enqueue')

    def __enter__(self):
        return self.format().to_console().start()

    def __exit__(self, *args):
        _ = args
        self.stop()


logger = _Logger()
atexit.register(logger.stop)
