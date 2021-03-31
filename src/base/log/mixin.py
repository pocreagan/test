import logging
import sys
from functools import wraps
from typing import Any, TypeVar
from typing import Union

from typing_extensions import Protocol

from src.base.log import logger
# noinspection PyProtectedMember
from src.base.log.main import _Logger
from src.base.register import before

__all__ = [
    'Logged',
]

_NAME_WIDTH = 40
_non_error_levels = ['debug', 'info', 'warning', 'warn']
_error_levels = ['error', 'critical']
_exception_levels = ['exception']


# SUPPRESS-LINTER <I want this base to look like any other type constant>
# noinspection PyPep8Naming
class LOG_ERROR_F_T(Protocol):
    """
    drop-in replacement for logging.Logger.error and .critical
    """

    def __call__(self, *s: Any, stack_info: int = 0) -> None: ...


# SUPPRESS-LINTER <I want this base to look like any other type constant>
# noinspection PyPep8Naming
class LOG_EXCEPTION_F_T(Protocol):
    """
    drop-in replacement for logging.Logger.error and .critical
    """

    def __call__(self, *s: Any) -> None: ...


LOG_NON_ERROR_F_T = LOG_EXCEPTION_F_T


def _make_log_f(f) -> Union[LOG_ERROR_F_T, LOG_EXCEPTION_F_T]:
    @wraps(f)
    def inner(*args, **kwargs) -> None:
        first, *rest = args
        if rest:
            return f(' '.join(map(str, args)), **kwargs)
        return f(str(first), **kwargs)

    # noinspection PyTypeChecker
    return inner  # type: ignore


class Logged:
    """
    Allows log origin to be meaningful in complex inheritance trees
    Any link in the hierarchy can call self.<method>(log_string),
    and it will show up with the terminal name.
    """
    # these symbols are bound in log_attach_object
    debug: LOG_NON_ERROR_F_T
    info: LOG_NON_ERROR_F_T
    warning: LOG_NON_ERROR_F_T
    warn: LOG_NON_ERROR_F_T
    error: LOG_ERROR_F_T
    exception: LOG_EXCEPTION_F_T
    critical: LOG_ERROR_F_T

    _T = TypeVar('_T')

    def log_level(self: _T, level: int) -> _T:
        self._logger.setLevel(level)
        return self

    @before('__init__')
    def _log_attach_object_(self, *, name: str = None) -> None:
        """
        if @name is provided, it should be given as builtin __name__
        switch type(@logger_):
            case <log from "log = logger_(__name__)">:
                pulls attrs directly from that self
            case <logger_ from "from src.base.log import logger_">:
                adds logger_ with computed name to existing tree and pulls attrs from that
            case <None>:
                simulates logger_ with computed name and binds sim funcs to attr names in obj.__dict__
        """
        if not name:
            # noinspection PyProtectedMember
            name = f'{_Logger._root}.' + (getattr(self, 'name', None) or type(self).__qualname__)

        logger_ = logger
        if logger_ is None:
            _print_name = name.ljust(_NAME_WIDTH, ' ')
            import traceback

            def named_print(s: str) -> None:
                """equivalent to log.instrument_debug"""
                print(f'{_print_name} -> {s}')

            def error_level(s: str, stack_info: int = False) -> None:
                """equivalent to log.error"""
                named_print(s)
                if stack_info:
                    traceback.print_exc(file=sys.stdout)

            def exception_level(s: str) -> None:
                """equivalent to log.exception"""
                named_print(s)
                traceback.print_exc(file=sys.stdout)

            [setattr(self, k, named_print) for k in _non_error_levels]
            [setattr(self, k, error_level) for k in _error_levels]
            [setattr(self, k, exception_level) for k in _exception_levels]

        else:
            _logger = logger_(name) if not isinstance(logger_, logging.Logger) else logger_

            for li_ in [_non_error_levels, _error_levels, _exception_levels]:
                [setattr(self, k, _make_log_f(getattr(_logger, k))) for k in li_]

            self._logger = _logger

            log_level = getattr(self, 'LOG_LEVEL', None)
            if log_level is not None:
                self.log_level = log_level
