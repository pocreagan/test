from dataclasses import dataclass
from typing import Callable, Dict, Any
from typing import Generic
from typing import Optional
from typing import Type
from typing import TypeVar

from typing_extensions import Literal

from src.base.db.connection import SessionManager
from src.base.db.connection import SessionType
from src.base.decorators import configure_class
from src.base.log.mixin import Logged
from src.instruments.base import instrument
from src.model.db.schema import TestIterationProtocol
from src.model.db.schema import TestStepProtocol
from src.model.db.schema import YamlFile

__all__ = [
    'TestStation',
    'TestStep',
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
    pass


class StationFailure(Failure):
    pass


@dataclass
class DUTIdentityModel:
    sn: int
    mn: int
    option: Optional[str] = None


_STEP_MODEL_T = TypeVar('_STEP_MODEL_T', bound=TestStepProtocol)


class TestStep(Generic[_STEP_MODEL_T]):
    step_failure_is_test_failure: bool
    step_model_cla: Type[_STEP_MODEL_T]

    def __init__(self, session: SessionType, test: 'TestStation', **instruments) -> None:
        self.session = session
        self.test = test
        configure_class(**instruments)(self)

    @classmethod
    def check_config(cls, **kwargs) -> None:
        """
        subclass.check_config should have specific kwargs required for execution
        should have no side effects apart from raising the normal TypeError on mismatch
        """
        raise NotImplementedError

    def run(self) -> None:
        """
        raise TestFailure(reason: str) if step fails
        unhandled exceptions are reraised as StationFailure
        """
        raise NotImplementedError

    def make_step_model(self) -> _STEP_MODEL_T:
        raise NotImplementedError

    def start_step(self) -> _STEP_MODEL_T:
        step_model = self.session.make(self.make_step_model())
        self.test.iteration.steps.append(step_model)
        return step_model

    def __call__(self, **config) -> None:
        self.check_config(**config)
        configure_class(**config)(self)
        step_model = self.start_step()

        try:
            try:
                self.run()

            except StepFailure as e:
                step_model.exception()
                if self.step_failure_is_test_failure:
                    raise TestFailure from e

            except Exception as e:
                raise StationFailure from e

        except (TestFailure, StationFailure):
            raise

        else:
            step_model.success = True
            self.session.flush()


class TestStation(instrument.InstrumentHandler, Logged):
    _iteration_model_cla: Type[TestIterationProtocol]

    session_manager: SessionManager
    unit: DUTIdentityModel
    model: Type
    session: SessionType
    iteration: TestIterationProtocol
    config: Dict[str, Any]

    def __init__(self, session_manager: SessionManager,
                 view_emit: Callable = None) -> None:
        self._emit = view_emit if callable(view_emit) else self.info
        self.session_manager = session_manager
        with self.session_manager() as session:
            YamlFile.update_object(session, self)
            [YamlFile.update_object(session, inst) for inst in self.instruments.values()]
        # noinspection PyTypeChecker
        self.model = self.build_test_model()

    def test_failure(self, msg) -> Literal[False]:
        self.emit(msg)
        return False

    def emit(self, msg: _T) -> _T:
        """
        send test updates to view, for example
        """
        self._emit('emitted', msg)
        return msg

    def run(self, unit: DUTIdentityModel) -> None:
        self.unit = unit

        try:
            with self.session_manager() as session:
                self.session = session
                self.iteration = self.session.make(self.get_test_iteration())
                self.perform_test(unit)

        except Exception as e:
            raise StationFailure(str(e)) from e

    def get_test_iteration(self) -> TestIterationProtocol:
        """
        build test iteration model from schema
        """
        raise NotImplementedError

    def perform_test(self, unit: DUTIdentityModel) -> None:
        """
        once DUT and test model have been set, run test steps
        """
        raise NotImplementedError

    def build_test_model(self):
        """
        build test model from unit identity from database config and params rows
        """
        raise NotImplementedError

    def instruments_setup(self) -> None:
        """
        setup work after the individual instruments set themselves up
        """
        raise NotImplementedError
