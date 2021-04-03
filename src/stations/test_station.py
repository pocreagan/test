from itertools import chain
from typing import Any
from typing import Callable
from typing import Dict
from typing import Generic
from typing import Optional
from typing_extensions import Protocol
from typing import Type
from typing import TypeVar

from typing_extensions import Literal

from src.base.db.connection import SessionManager
from src.base.db.connection import SessionType
from src.base.decorators import configure_class
from src.base.log.mixin import Logged
from src.instruments.base import instrument
from src.model.db.schema import AppConfigUpdate
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


class DUTIdentityModel(Protocol):
    sn: int
    mn: int
    option: Optional[str] = None


_STEP_MODEL_T = TypeVar('_STEP_MODEL_T')


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
    model_builder_t: Type
    model_builder: Any
    session_manager: SessionManager
    unit: DUTIdentityModel
    models: Any
    iteration: Any
    session: SessionType
    config: Dict[str, Any]

    def __init__(self, session_manager: SessionManager,
                 view_emit: Callable = None) -> None:
        self._emit = view_emit if callable(view_emit) else self.info
        self.session_manager = session_manager
        with self.session_manager() as session:
            [YamlFile.update_object(session, inst) for inst in chain([self], self.instruments.values())]
            self.config_rev = AppConfigUpdate.get(session).id
        # noinspection PyTypeChecker
        self.model_builder = self.model_builder_t(self.session_manager)

    def test_failure(self, msg) -> Literal[False]:
        self.emit(msg)
        return False

    def emit(self, msg: _T) -> _T:
        """
        send test updates to view, for example
        """
        self._emit('emitted', msg)
        return msg

    def on_test_failure(self, e: Exception) -> None:
        self.emit(str(e))

    def run(self, unit: DUTIdentityModel):
        self.models = self.model_builder()
        self.iteration_setup(unit)
        try:
            self.perform_test()

        except TestFailure as e:
            self.on_test_failure(e)

        except Exception as e:
            raise StationFailure(str(e)) from e

        with self.session_manager() as session:
            session.add(self.iteration)

        return self.iteration

    def iteration_setup(self, unit: DUTIdentityModel):
        """
        build test iteration model from schema and configs
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
