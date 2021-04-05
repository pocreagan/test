from dataclasses import dataclass
from itertools import chain
from typing import Any
from typing import Callable
from typing import Dict
from typing import Generic
from typing import Optional
from typing import Type
from typing import TypeVar

from typing_extensions import Protocol

from model.vc_messages import StepFinishMessage
from src.base.db.connection import SessionManager
from src.base.db.connection import SessionType
from src.base.log.mixin import Logged
from src.instruments.base import instrument
from src.model.db.schema import AppConfigUpdate
from src.model.db.schema import YamlFile

__all__ = [
    'TestStation',
    'DUTIdentityModel',
    'TestFailure',
    'StepFailure',
    'StationFailure',
]

_T = TypeVar('_T')


class Failure(Exception):
    pass


class StepFailure(Failure):
    pass


class TestFailure(Failure):
    def __init__(self, message, test_step_id: int = None):
        super().__init__(message)
        self.test_step_id = test_step_id


class StationFailure(Failure):
    pass


class DUTIdentityModel(Protocol):
    sn: int
    mn: int
    option: Optional[str] = None


_IT = TypeVar('_IT')
_MT = TypeVar('_MT')


class TestStation(instrument.InstrumentHandler, Logged, Generic[_MT, _IT]):
    model_builder_t: Type[_MT]
    model_builder: _MT
    iteration_t: Type[_IT]
    iteration: _IT
    session_manager: SessionManager
    unit: DUTIdentityModel
    model: dataclass
    session: SessionType
    config: Dict[str, Any]
    _test_step_k: int

    def __init__(self, session_manager: SessionManager,
                 controller_q: Callable = None, controller_flag=None) -> None:
        self._emit = controller_q if callable(controller_q) else self.info
        self._controller_flag = controller_flag
        self.session_manager = session_manager
        with self.session_manager() as session:
            [YamlFile.update_object(session, inst) for inst in chain([self], self.instruments.values())]
            self.config_rev = AppConfigUpdate.get(session).id
        # noinspection PyTypeChecker
        self.model_builder = self.model_builder_t(self.session_manager)

    def emit(self, msg: _T) -> _T:
        """
        send test updates to view, for example
        """
        self._emit(msg)
        return msg

    def on_test_failure(self, e: Exception) -> None:
        self.emit(StepFinishMessage(k=self._test_step_k, success=False))
        self.emit(str(e))

    def increment_test_step_k(self) -> None:
        self._test_step_k += 1

    def setup(self, unit: DUTIdentityModel) -> None:
        self.unit = unit
        self.model = self.model_builder.for_dut(self.unit)

    def cooldown_check(self) -> None:
        try:
            self.perform_cooldown_check()

        except TestFailure as e:
            self.on_test_failure(e)

        except Exception as e:
            raise StationFailure(str(e)) from e

    def connection_check(self) -> None:
        try:
            self.perform_connection_check()

        except TestFailure as e:
            self.on_test_failure(e)

        except Exception as e:
            raise StationFailure(str(e)) from e

    def run(self):
        self.iteration = self.iteration_t()
        self.iteration.dut = self.unit
        self._test_step_k = 0
        try:
            self.perform_test()

        except TestFailure as e:
            self.on_test_failure(e)
            self.connection_check()

        except Exception as e:
            raise StationFailure(str(e)) from e

        with self.session_manager() as session:
            session.add(self.iteration)

        return self.iteration

    def perform_cooldown_check(self) -> None:
        """
        after dut has been set, check for previous test times
        raise TestError if DUT was tested too recently
        """
        raise NotImplementedError

    def perform_connection_check(self) -> None:
        """
        once DUT and test model have been set, check for connection
        raise TestFailure if connection is not proven
        """
        raise NotImplementedError

    def perform_test(self) -> None:
        """
        once DUT and test model have been set, run test steps
        """
        raise NotImplementedError

    def instruments_setup(self) -> None:
        """
        setup work after the individual instruments set themselves up
        """
        raise NotImplementedError
