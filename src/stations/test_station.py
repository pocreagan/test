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

from src.model.vc_messages import StepsInitMessage
from src.base.concurrency import proxy
from src.base.db.connection import SessionManager
from src.base.db.connection import SessionType
from src.instruments.base import instrument
from src.model.db.schema import AppConfigUpdate
from src.model.db.schema import YamlFile
from src.model.vc_messages import StepFinishMessage

__all__ = [
    'TestStation',
    'DUTIdentityModelProtocol',
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


class DUTIdentityModelProtocol(Protocol):
    sn: int
    mn: int
    option: Optional[str] = None


_IT = TypeVar('_IT')
_MT = TypeVar('_MT')


class TestStation(instrument.InstrumentHandler, Generic[_MT, _IT]):
    model_builder_t: Type[_MT]
    model_builder: _MT
    iteration_t: Type[_IT]
    iteration: _IT
    session_manager: SessionManager
    unit: DUTIdentityModelProtocol
    model: dataclass
    session: SessionType
    config: Dict[str, Any]

    def __init__(self, session_manager: SessionManager,
                 controller_q: Callable = None, view_q: Callable = None) -> None:
        self._emit = view_q if callable(view_q) else self.info
        self._controller_q = controller_q
        self.session_manager = session_manager
        with self.session_manager() as session:
            [YamlFile.update_object(session, inst) for inst in chain([self], self.instruments.values())]
            self.config_rev = AppConfigUpdate.get(session).id
        # noinspection PyTypeChecker
        self.model_builder = self.model_builder_t(self.session_manager)

    def emit(self, msg: _T) -> _T:
        """
        send test updates to view
        """
        self._emit(msg)
        return msg

    def on_test_failure(self, e: TestFailure) -> None:
        if e.test_step_id is not None:
            self.emit(StepFinishMessage(
                k=e.test_step_id,
                success=False
            ))
        self.emit(e)

    def on_unhandled_exception(self, e: Exception) -> None:
        raise StationFailure(str(e)) from e

    @proxy.exposed
    def setup(self, unit: DUTIdentityModelProtocol) -> None:
        self.unit = unit
        self.model, for_chart = self.model_builder.for_dut(self.unit)
        self.emit(for_chart)
        self.emit(self.unit)
        self.emit(StepsInitMessage(self.model.step_ids.for_view))

    @proxy.exposed
    def connection_check(self) -> bool:
        try:
            self.perform_connection_check()

        except TestFailure as e:
            self.on_test_failure(e)
            return False

        except Exception as e:
            self.on_unhandled_exception(e)

        return True

    @proxy.exposed
    def run(self):
        self.iteration = self.iteration_t()
        self.iteration.dut = self.unit
        try:
            self.perform_test()

        except TestFailure as e:
            self.on_test_failure(e)
            self.connection_check()

        except Exception as e:
            self.on_unhandled_exception(e)

        with self.session_manager(expire=False) as session:
            return session.make(self.iteration)

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
