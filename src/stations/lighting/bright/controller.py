import datetime
from random import choice
from random import randint
from typing import *

from framework.base.general import random_condition
from framework.base.concurrency import *
from framework.base.message import ControllerAction
from framework.base.message import Message
from framework.base.message import ViewAction
from framework.model import *

__all__ = [
    'Controller',
]


log = logger(__name__)

TEST_RUN_D_T = dict[str, Union[int, bool, datetime.datetime, str, str]]


class BoolDict(dict):
    @classmethod
    def fromkeys(cls, ks, v) -> 'BoolDict':
        self = cls()
        for k in ks:
            self[k] = v
        return self

    @property
    def all_true(self) -> bool:
        return all(self.values())

    @property
    def all_false(self) -> bool:
        return not any(self.values())

    @property
    def all_none(self):
        return all(v is None for v in self.values())


class CellCounterpart(ChildTerminus):
    def __post_init__(self, *args, **kwargs) -> None:
        """
        subclass specific setup here
        """

    def __init__(self, parent: 'Controller', *args, **kwargs):
        self.parent: 'Controller' = parent
        self.parent.children.append(self)
        self.perform_view_action = self._perform_other_action
        self.__post_init__(*args, **kwargs)

    def poll(self) -> None:
        """
        performs on every parent.poll()
        """

    def close(self) -> None:
        """
        performed on parent.close()
        """


class History(CellCounterpart):
    def __post_init__(self) -> None:
        self.sns = [str(randint(2 ** 23, 2 ** 24 - 1)).zfill(8) for _ in range(5)]

    def _make_one(self, fresh: bool = False) -> TEST_RUN_D_T:
        dt = datetime.datetime.now()
        if not fresh:
            # dt -= datetime.timedelta(hours=randint(0, 8), minutes=randint(0, 59), seconds=randint(0, 59))
            dt -= datetime.timedelta(minutes=randint(0, 59), seconds=randint(0, 59))
        return dict(
            id=randint(100, 100000000),
            pf=bool(randint(0, 1)),
            dt=dt,
            mn='10-00938' if randint(0, 1) else '10-00962',
            sn=choice(self.sns),
        )

    def all(self) -> None:
        data = [self._make_one() for _ in range(randint(20, 40))]
        data.sort(key=lambda r: r['dt'])
        self.perform_view_action(self, 'initialize_history', data)

    def new(self) -> None:
        self.perform_view_action(self, 'add_one_to_history', self._make_one(True))


class Instruments(ThreadHandler, CellCounterpart):
    thread_classes: dict[str, Any]

    def __post_init__(self, instruments: list[str]) -> None:
        from framework.controller import equipment

        self._instruments_list = instruments
        self._te_ready_dict = BoolDict.fromkeys(self._instruments_list, None)
        self.closed = self._te_ready_dict.all_none
        self.ready = self._te_ready_dict.all_true

        self.thread_classes = {k: getattr(equipment, k) for k in self._instruments_list}

        ThreadHandler.__post_init__(self)

    def close_result(self, msg: Message.ResponseRequired, name: str):
        self._te_ready_dict[name] = None
        _ = msg

    def close_one(self, name: str) -> None:
        self._te_ready_dict[name] = False
        self.perform_thread_action(name, self.thread_classes[name].Messages.Close(),
                                   self.close_result, **dict(name=name))

    # def close(self):
    #     [self.close_one(name) for name in self._instruments_list]

    def check_result(self, msg: Message.ResponseRequired, name: str):
        self._te_ready_dict[name] = msg.is_success
        self.perform_view_action(self, 'update_instrument', name, 'good' if msg.is_success else 'bad')

    def check_one(self, name: str) -> None:
        self._te_ready_dict[name] = False
        self.perform_thread_action(name, self.thread_classes[name].Messages.Check(),
                                   self.check_result, **dict(name=name))
        self.perform_view_action(self, 'update_instrument', name, 'checking')

    def check(self) -> None:
        [self.check_one(name) for name in self._instruments_list]


class Mode(CellCounterpart):
    def change(self, msg: ControllerAction):
        if msg == 'rework':
            major, minor = 'not in test mode', 'scan DUT to view results'
        else:
            major, minor = 'ready to test', 'scan DUT to continue'
        self.perform_view_action('instruction', 'set', major, minor)
        log.info(f'performing {msg}')


class TestSteps(CellCounterpart):
    steps = {
        'AUTODETECT': 100,
        'FIRMWARE': 100,
        'RAW CONFIGURATION': 100,
        'THERMAL TEST': 100,
        'STRING TEST': 100,
    }

    def __post_init__(self, *args, **kwargs) -> None:
        self.step_names = list(self.steps.keys())
        self.step_values = [0] * len(self.steps)
        self.index = 0

    def update_step(self) -> None:
        step, value = self.step_names[self.index], self.step_values[self.index]
        if value == 0:
            self.perform_view_action(self, 'start_progress', step)
        if value < 100:
            self.perform_view_action(self, 'increment', step)
            self.step_values[self.index] += 1
        if value == 100:
            result = 'result_pass' if random_condition() else 'result_fail'
            self.perform_view_action(self, result, step)
            self.index += 1
        if self.index < len(self.steps):
            self.parent.schedule(.05, self.update_step)

    def get_steps(self):
        self.perform_view_action(self, 'make_steps', self.steps)
        self.parent.schedule(.1, self.update_step)


class Controller(parent_terminus(ControllerAction, ViewAction), Process):  # type: ignore
    def poll(self) -> None:
        Process.poll(self)
        [o.poll() for o in self.children]

    def __post_init__(self):
        self._poll_delay_s = APP.G.POLLING_INTERVAL_MS / 1000
        self.perform_view_action = getattr(self, '_perform_other_action')

        self.children = list()

        self.mode = Mode(self)
        self.history = History(self)
        self.test_steps = TestSteps(self)
        self.instruments = Instruments(self, APP.STATION.instruments)

        logger.to_main_process(self._log_q).start()
        Process.__post_init__(self)

    def on_shutdown(self):
        [o.close() for o in self.children]

    def __init__(self, log_q):
        Process.__init__(self, log_q, name='Controller', log_name=__name__)
