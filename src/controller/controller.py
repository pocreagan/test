import datetime
import re
from dataclasses import dataclass
from dataclasses import fields
from random import choice
from random import randint
from typing import *

from model.db import connect
from src.base import atexit_proxy
from src.base.concurrency.concurrency import *
from src.base.concurrency.message import ControllerAction
from src.base.concurrency.message import Message
from src.base.concurrency.message import ViewAction
from src.base.general import random_condition
from src.base.log import logger
from src.controller.base.decorators import scan_method
from src.controller.base.decorators import subscribe
from src.controller.messages import *
from src.model.resources import APP

__all__ = [
    'Controller',
]

# TODO: history db->view
# TODO: pubsub in View and Controller
# TODO: add thread wrapping to TestStation
# TODO: make test steps start, result, update messages
# TODO: TE check and start test messages
# TODO: test thread handler
# TODO: try old matplotlib version for binary build
# TODO: chart updates and FA methods/messages
# TODO: make label program for new DUT scans
# TODO: main CLI or system name -> test station package cfg map
# TODO: sqlite -> postgres


log = logger(__name__)

TEST_RUN_D_T = Dict[str, Union[int, bool, datetime.datetime, str, str]]


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


_sns = [str(randint(2 ** 23, 2 ** 24 - 1)).zfill(8) for _ in range(5)]


def _make_one(fresh: bool = False) -> OneHistoryMessage:
    dt = datetime.datetime.now()
    if not fresh:
        # dt -= datetime.timedelta(hours=randint(0, 8), minutes=randint(0, 59), seconds=randint(0, 59))
        dt -= datetime.timedelta(minutes=randint(0, 59), seconds=randint(0, 59))
    return OneHistoryMessage(
        id=randint(100, 100000000),
        pf=bool(randint(0, 1)),
        dt=dt,
        mn='10-00938' if randint(0, 1) else '10-00962',
        sn=choice(_sns),
    )


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


class Controller(parent_terminus(ControllerAction, ViewAction), Process):
    scan_methods: List[Tuple[str, re.Pattern]]
    subscribed_methods: Dict[Type, str]
    iteration_t: Type
    _station_mode: StationMode

    @scan_method(re.compile(r'(?i)\[DUT#\|(\d{5}):(\d{8})]'))
    def old_dut_scan(self, mn: str, sn: str) -> None:
        pass

    @scan_method(re.compile(r'(?i)\[DUT\|(\d{5}):(\d{8}):(.{12})]'))
    def dut_scan(self, mn: str, sn: str, option: str) -> None:
        pass

    @scan_method(re.compile(r'(?i)\[PSU#\|(\w{4}):(\d{3})-(\d{4})]'))
    def psu_label_scan(self, job_code: str, shipment: str, sn: str):
        pass

    @subscribe(ScanMessage)
    def scan(self, scan_string: str) -> None:
        for f, pattern in self.scan_methods or []:
            parsed = pattern.findall(scan_string)
            if parsed:
                log.info(f'handling scan -> {f}{tuple(parsed[0])}')
                return getattr(self, f)(*parsed[0])

        log.info(f'unhandled scan -> {scan_string}')

    @subscribe(GetFullHistoryMessage)
    def get_history(self) -> None:
        # TODO: get and format records from database
        self.send(FullHistoryMessage(records=[_make_one() for _ in range(randint(20, 40))]))

    @subscribe(ModeChangeMessage)
    def mode_change(self, mode: StationMode):
        if not self.is_testing:
            if mode == StationMode.REWORK:
                self.send(InstructionMessage('not in test mode', 'scan DUT to view results'))
            else:
                self.send(InstructionMessage('ready to test', 'scan DUT to continue'))
        self._station_mode = mode
        self.send(ModeChangeMessage(self._station_mode))
        log.info(f'changed to {mode}')

    @subscribe(TECheckMessage)
    def te_check(self) -> None:
        pass

    def add_one_to_history(self) -> None:
        self.send(_make_one(True))

    def handle_message(self, msg: dataclass) -> None:
        method = getattr(self, self.subscribed_methods[type(msg)], None)
        if callable(method):
            method(*fields(msg))
        log.warning(f'{msg} unhandled')

    def send(self, message: dataclass) -> None:
        log.info(f'sending {message}')
        self.q.put(message)

    def __post_init__(self):
        self._poll_delay_s = APP.G['POLLING_INTERVAL_MS'] / 1000
        self.perform_view_action = getattr(self, '_perform_other_action')

        self.children = list()
        self.is_testing = False
        self._station_mode = StationMode.TESTING

        self.test_steps = TestSteps(self)
        # self.instruments = Instruments(self, APP.STATION.instruments)

        self.session_manager = connect()

        logger.to_main_process(self._log_q).start()
        Process.__post_init__(self)

    def on_shutdown(self):
        [o.close() for o in self.children]
        atexit_proxy.perform(log)

    def __init__(self, log_q):
        Process.__init__(self, log_q, name='Controller', log_name=__name__)
