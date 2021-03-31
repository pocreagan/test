import datetime
from functools import lru_cache
from typing import Any
from typing import Callable
from typing import Dict
from typing import List
from typing import Optional
from typing import Type
from typing import Union
from uuid import uuid4

import stringcase

from src.base.general import EqEnum

__all__ = [
    'Message',
    'KeyboardAction',
    'MouseAction',
    'LayeredAction',
    'ViewAction',
    'ControllerAction',
    'HID_ACTION',
]

PICKLE_STATE = [dict, dict]


class MessageMeta(type):
    name: str

    def __new__(mcs, name, bases, d):
        _d = d.copy()
        _d.update(dict(name=name, snake_case=stringcase.snakecase(name),
                  __instance_check_key=12345678))
        return super().__new__(mcs, name, bases, _d)

    def __instancecheck__(self, other):
        if hasattr(other, '__instance_check_key'):
            return self.name == other.name
        return False


class Message:
    class CastField:
        def __init__(self, _type: type, rounding: int = None):
            self.type, self.rounding = _type, rounding
            if self.rounding is not None:
                assert self.type is float, 'only floats can be rounded'

        def cast(self, v):
            v = self.type(v)
            if self.rounding is not None:
                v = float(round(v, self.rounding))
            return v

    @classmethod
    @lru_cache(maxsize=128, typed=False)
    def cast_field(cls, _type: type, rounding: int = None) -> 'Message.CastField':
        return cls.CastField(_type, rounding)

    class Base(metaclass=MessageMeta):
        _p_args = ['_ti', '_TIMEOUT_IN_SECONDS', 'id', ]

        _fields: List[str] = None
        _ti: datetime.datetime
        _TIMEOUT_IN_SECONDS: float = None
        snake_case: str
        name: str

        _CAST_FIELDS: Dict[str, 'Message.CastField'] = None
        _VALIDATORS: Dict[str, Callable] = None

        @property
        def is_timeout_condition(self) -> bool:
            if self._TIMEOUT_IN_SECONDS is not None:
                return self.seconds_elapsed_since() > self._TIMEOUT_IN_SECONDS
            return False

        @staticmethod
        def _make_time() -> datetime.datetime:
            return datetime.datetime.now()

        @staticmethod
        def format_te(seconds: float) -> str:
            seconds = float(seconds)
            multiplier, string = (1, 's') if seconds >= 1. else (1000, 'ms')
            return '{t:.03f}{string}'.format(t=seconds * multiplier, string=string)

        def seconds_elapsed_since(self, tf: datetime.datetime = None) -> float:
            return ((tf or getattr(self, '_tf', None) or self._make_time()) - self._ti).total_seconds()

        @staticmethod
        def _make_one_field(k: str, v) -> str:
            if k == 'T_ELAPSED':
                return f'{Message.Base.format_te(v)} elapsed'
            if k == 'FAILED_TO_VALIDATE_FIELDS':
                return str(v)
            if isinstance(v, str):
                return f'{k}="{v}"'
            return f'{k}={v}'

        def _make_str(self) -> str:
            s = self.name
            return s + f'({",".join([self._make_one_field(k, getattr(self, k)) for k in self._fields])})'

        def __str__(self) -> str:
            return self._make_str()

        def __repr__(self) -> str:
            return str(self)

        def _validate_one(self, k: str, v) -> bool:
            """
            __perform_task validations on attributes set in .add
            """
            if k in self._VALIDATORS:
                is_valid = self._VALIDATORS[k](v)
                if not isinstance(is_valid, bool):
                    raise ValueError(f'validation of {{{k} = {v}}} must return bool')
                return is_valid
            return True

        def _add_to_failed_to_validate(self, k: str) -> None:
            if 'FAILED_TO_VALIDATE_FIELDS' not in self._fields:
                self._add_one('FAILED_TO_VALIDATE_FIELDS', set())
            self.FAILED_TO_VALIDATE_FIELDS.add(k)

        def _add_one(self, k: str, v) -> 'Message.Base':
            caster = self._CAST_FIELDS.get(k, None)
            if caster is not None:
                v = caster.cast(v)
            if not self._validate_one(k, v):
                self._add_to_failed_to_validate(k)
            setattr(self, k, v)
            if k not in self._fields:
                self._fields = [*self._fields, k]
            return self

        def add(self, **kwargs) -> 'Message.Base':
            [self._add_one(k, v) for k, v in kwargs.items()]
            if self.FAILED_TO_VALIDATE_FIELDS:
                raise ValueError(f'failed to validate field(s): {self.FAILED_TO_VALIDATE_FIELDS}')
            return self

        def _process_request_values(self) -> None:
            """
            __perform_task calculations on initial data
            """

        def mark_begun(self) -> 'Message.Base':
            self._ti = self._make_time()
            return self

        def __getstate__(self) -> PICKLE_STATE:
            fields, p_args = [{k: getattr(self, k) for k in li} for li in (self._fields, self._p_args)]
            return fields, p_args

        def __setstate__(self, state: PICKLE_STATE) -> 'Message.Base':
            fields, pickle_args = state
            self._start()
            self.add(**fields)
            [setattr(self, k, v) for k, v in pickle_args.items()]
            return self

        def _start(self):
            self._CAST_FIELDS = self._CAST_FIELDS or {}
            self._VALIDATORS = self._VALIDATORS or {}
            self.FAILED_TO_VALIDATE_FIELDS = set()
            self._fields = self._fields or []

        def __init__(self, **kwargs):
            self._start()
            self.id = str(uuid4())
            self.add(**kwargs)
            self._process_request_values()
            self.mark_begun()

        def __eq__(self, other: 'Message.Base') -> bool:
            if hasattr(other, 'id'):
                return self.id == other.id
            return object.__eq__(self, other)

    class Notification(Base):
        pass

    class ResponseRequired(Base):
        is_success: Optional[bool]
        T_ELAPSED: float
        _tf: datetime.datetime = None
        _p_args = ['_ti', '_tf', '_TIMEOUT_IN_SECONDS', 'id', ]

        def _mark_complete(self, is_successful: bool):
            self.is_success = is_successful
            self._tf = self._make_time()
            self.add(T_ELAPSED=self.seconds_elapsed_since())
            return self

        def mark_begun(self):
            return super().mark_begun().add(is_success=None)

        def success(self):
            return self._mark_complete(True)

        def failure(self):
            return self._mark_complete(False)

        def exception(self, e: Union[Exception, Type[Exception]] = None):
            if str(e):
                return self.add(ERROR=e or Exception).failure()
            return self.add(ERROR=e.__class__.__name__).failure()

    class Command(ResponseRequired):
        pass

    class Request(ResponseRequired):
        def process_response_values(self) -> Optional[bool]:
            """
            __perform_task calculations on response data
            if this returns True, message is marked as successful
            """
            _ = self
            return True

        def _process_response_values(self) -> bool:
            try:
                return self.process_response_values()
            except Exception as e:
                self.exception(e)
                return False

        def _check(self):
            return (self.success if self._process_response_values() is not False else self.failure)()

        def set(self, **kwargs):
            self.add(**kwargs)
            self._check()
            return self


class KeyboardAction(Message.Notification):
    f: str
    args: tuple
    kwargs: Dict[str, Any]

    def __init__(self, f: str, *args, **kwargs) -> None:
        super().__init__(f=f, args=args, kwargs=kwargs)


class MouseAction(Message.Notification):
    widget: str
    action: EqEnum

    def __init__(self, widget: str, action: EqEnum) -> None:
        super().__init__(widget=widget, action=action)


HID_ACTION = Union[KeyboardAction, MouseAction]


class LayeredAction(Message.Command):
    """
    if object is None, __perform_task on self
    """
    o: Optional[str]
    f: str
    args: tuple
    kwargs: Dict[str, Any]

    def __init__(self, o: Optional[str], f: str, *args, **kwargs) -> None:
        super().__init__(o=o, f=f, args=args, kwargs=kwargs)


class ViewAction(LayeredAction):
    """"""


class ControllerAction(LayeredAction):
    """"""
