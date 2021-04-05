import datetime
import re
import time
from dataclasses import asdict
from queue import Queue
from random import choice
from random import randint
from typing import *

from typing_extensions import Literal

from src.model.db.schema import LightingStation3ResultRow
from src.base import atexit_proxy
from src.base.concurrency.concurrency import *
from src.base.log import logger
from src.controller.base.decorators import scan_method
from src.controller.base.decorators import subscribe
from src.model.db import connect
from src.model.db.schema import LightingDUT
from src.model.db.schema import LightingStation3Iteration
from src.model.resources import APP
from src.model.vc_messages import *

__all__ = [
    'Controller',
]

# TODO: add thread wrapping to TestStation
# TODO: make test steps start, result, update messages
# TODO: TE check message
# TODO: chart updates and FA methods/messages
# TODO: make label program for new DUT scans
# TODO: main CLI or system name -> test station package cfg map
# TODO: sqlite -> postgres

log = logger(__name__)

TEST_RUN_D_T = Dict[str, Union[int, bool, datetime.datetime, str, str]]
_sns = [str(randint(2 ** 23, 2 ** 24 - 1)).zfill(8) for _ in range(5)]


def _make_one_fake_entry(fresh: bool = False) -> HistoryAddEntryMessage:
    dt = datetime.datetime.now()
    if not fresh:
        dt -= datetime.timedelta(minutes=randint(0, 59), seconds=randint(0, 59))
    return HistoryAddEntryMessage(
        id=randint(100, 100000000), pf=bool(randint(0, 1)), dt=dt,
        mn='10-00938' if randint(0, 1) else '10-00962', sn=choice(_sns),
    )


class Controller(Process):
    scan_methods: List[Tuple[str, re.Pattern]]
    subscribed_methods: DefaultDict[Union[Literal['parent'], Literal['child']], Dict[Type, str]]
    iteration_t: Type
    _station_mode: StationMode
    _iteration_cla: Type[LightingStation3Iteration] = LightingStation3Iteration
    _dut_cla: Type[LightingDUT] = LightingDUT

    _poll_delay_s = APP.G['POLLING_INTERVAL_MS'] / 1000

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

    @subscribe(HistoryGetAllMessage)
    def get_history(self) -> None:
        # response = HistorySetAllMessage([])
        # with self.session_manager() as session:
        #     results: List[LightingStation3Iteration] = session.query(
        #         self._iteration_cla, self._dut_cla
        #     ).outerjoin(self._iteration_cla.dut).order_by(self._iteration_cla.created_at).limit(100).all()
        #     for result in results:
        #         response.records.append(HistoryAddEntryMessage(
        #             result.id, bool(result.pf), result.created_at,
        #             f'10-0{str(result.dut.mn).zfill(4)}', str(result.dut.sn).zfill(8),
        #         ))
        #     return self.publish(response)
        self.publish(HistorySetAllMessage(records=[_make_one_fake_entry() for _ in range(randint(20, 40))]))

    @subscribe(ModeChangeMessage)
    def mode_change(self, mode: StationMode):
        if not self.is_testing:
            if mode == StationMode.REWORK:
                self.publish(InstructionMessage('not in test mode', 'scan DUT to view results'))
            else:
                self.publish(InstructionMessage('ready to test', 'scan DUT to continue'))
        self._station_mode = mode
        self.publish(ModeChangeMessage(self._station_mode))
        log.info(f'changed to {mode}')

    @subscribe(TECheckMessage)
    def te_check(self) -> None:
        pass

    @subscribe(GetMetricsMessage)
    def give_metrics(self) -> None:
        # response = MetricsMessage(0, 0, 0, 0)
        # midnight = datetime.datetime.combine(datetime.date.today(), datetime.datetime.min.time())
        # hour_ago = datetime.datetime.now() - datetime.timedelta(hours=1)
        # with self.session_manager() as session:
        #     for result in session.query(
        #             self._iteration_cla
        #     ).filter(self._iteration_cla.created_at >= midnight).all():
        #         if result.p_pf:
        #             response.pass_day += 1
        #             if result.created_at >= hour_ago:
        #                 response.pass_hour += 1
        #         else:
        #             response.fail_day += 1
        #             if result.created_at >= hour_ago:
        #                 response.fail_hour += 1
        #     self.publish(response)
        self.publish(MetricsMessage(randint(10, 20), 2, 151, 10))

    def is_cooldown_done(self, dut, cooldown_interval: float) -> bool:
        # with self.session_manager() as session:
        #     result = session.query(self._iteration_cla).filter_by(
        #         dut_id=dut.id
        #     ).order_by(self._iteration_cla.created_at).one_or_none()
        #     if result is None:
        #         return True
        #     return (datetime.datetime.now() - datetime.timedelta(
        #         seconds=cooldown_interval)) > result.created_at
        _ = self
        return True

    def send_steps(self):
        log.info('publishing steps init message')
        self.publish(StepsInitMessage(['AUTODETECT',
                                       'FIRMWARE',
                                       'RAW CONFIGURATION',
                                       'THERMAL TEST',
                                       'STRING TEST']))

    def add_one_to_history(self) -> None:
        self.publish(_make_one_fake_entry(True))

    def poll(self) -> None:
        Process.poll(self)
        if time.time() > self._next_chart_message:
            try:
                self.publish(next(self.messages_iter))
            except StopIteration:
                pass
            self._next_chart_message = time.time() + .05

    def handle_message(self, message) -> None:
        return self._handle_message(message, 'parent')

    def _handle_message(self, message, k: Union[Literal['child'], Literal['parent']]) -> None:
        method_name = self.subscribed_methods[k].get(type(message), None)
        if method_name is not None:
            method = getattr(self, method_name, None)
            if callable(method):
                args = asdict(message)
                return method(**args)
        log.warning(f'{message} from {k} unhandled')

    def handle_child_message(self, message):
        return self._handle_message(message, 'child')

    def publish(self, message) -> None:
        log.info(f'sending {message}')
        self._q.put(message)

    def __post_init__(self):
        self.is_testing = False
        self._station_mode = StationMode.TESTING

        self.session_manager = connect()
        self.test_station_q = Queue()

        with self.session_manager(expire=False) as session:
            iteration: LightingStation3Iteration = session.query(LightingStation3Iteration).first()
            _ = [f.firmware for f in iteration.firmware_iterations]
            _ = [c.config for c in iteration.config_iterations]
            _ = iteration.unit_identity_confirmations
            _ = [r.param_row for r in iteration.result_rows]
            dut: LightingDUT = iteration.dut
            messages = [dut]
            for measurement in iteration.result_rows:  # type: LightingStation3ResultRow
                messages.extend([*measurement.light_measurements, measurement])
            messages.append(iteration)
            # self.messages_iter = iter(messages)
            self.messages_iter = iter([])
            self._next_chart_message = time.time() + .05

        self.send_steps()
        self.get_history()

        logger.to_main_process(self._log_q).start()
        Process.__post_init__(self)

    def on_shutdown(self):
        atexit_proxy.perform(self.log)

    def __init__(self, log_q):
        Process.__init__(self, log_q, name='Controller', log_name=__name__)
