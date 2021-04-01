import threading
from multiprocessing import current_process
from typing import Callable
from typing import Dict
from typing import Tuple

__all__ = [
    'register',
    'unregister',
]

_process = current_process().name

if _process == 'MainProcess':
    from atexit import register, unregister

else:
    _registered_funcs: Dict[int, Tuple[Callable, Tuple, Dict]] = {}
    _lock = threading.RLock()


    def register(f: Callable, *args, **kwargs) -> None:
        with _lock:
            _registered_funcs[id(f)] = f, args, kwargs


    def unregister(f: Callable) -> None:
        with _lock:
            _id = id(f)
            if _id in _registered_funcs:
                del _registered_funcs[_id]


    def perform(logger=None) -> None:
        with _lock:
            for f, args, kwargs in _registered_funcs.values():
                # SUPPRESS-LINTER <catch and log all errors>
                # noinspection PyBroadException
                try:
                    f(*args, **kwargs)
                except Exception:
                    if hasattr(logger, 'exception'):
                        logger.exception(f'{__name__} performing {f.__name__} from {_process}', stack_info=1)
                else:
                    if hasattr(logger, 'info'):
                        logger.info(f'{__name__} performed {f.__name__} from {_process}')
