import csv
import logging
import queue
import winsound
from dataclasses import asdict
from datetime import datetime
from operator import itemgetter
from time import sleep
from typing import cast
from typing import Dict
from typing import List

import pandas as pd
from progressbar import progressbar

from model import configuration
from src.base.concurrency.concurrency import ConnectionClosed
from src.base.concurrency.concurrency import SentinelReceived
from src.base.concurrency.concurrency import ThreadConnection
from src.base.log import logger
from src.stations.test_station import TestInstrument
from src.stations.test_station import TestStation
from src.instruments.dc_power_supplies import DCLevel
from src.instruments.dc_power_supplies.bk_ps import BKPowerSupply
from src.instruments.light_meter import LightMeter
from src.instruments.wet.nfc import NFC
from src.instruments.wet.rs485 import RS485
from src.stations.lighting.pixie_hack import messages

log = logger(__name__)

param_header = [
    'row',
    'name',
    'row',
    'v',
    'i',
    'ch_mask',
    'x',
    'y',
    'color_dist_max',
    'fcd_nom',
    'fcd_tol',
    'p_nom',
    'p_tol',
]

result_header = [
    'dut_id',
    't',
    'row',
    'x',
    'y',
    'dist',
    'fcd',
    'p',
    'dist_pf',
    'fcd_pf',
    'p_pf',
    'row_pf',
    'test_pf',
]

assoc_table_header = [
    'dut_id',
    'uid',
    'test_pf',
]


class Pixie2pt0Station(TestStation):
    bk = TestInstrument(BKPowerSupply(), logging.INFO)
    lm = TestInstrument(LightMeter(), logging.INFO)
    ftdi = TestInstrument(RS485(), logging.DEBUG)
    nfc = TestInstrument(NFC(), logging.INFO)

    _config = configuration.from_yml('pixie_hack/.yml')
    TESTING_FW_PATH = _config.field(str)
    PRODUCTION_FW_PATH = _config.field(str)
    RESULT_PATH = _config.field(str)
    PARAMS_PATH = _config.field(str)
    ASSOCIATION_TABLE_PATH = _config.field(str)
    POWER_ON_WAIT_S = _config.field(float)
    CH_SETTLE_WAIT_S = _config.field(float)
    AFTER_ERASE_WAIT_S = _config.field(float)
    PROGRAMMING_V = _config.field(float)
    PROGRAMMING_I = _config.field(float)

    def set_power_supply_for_programming(self) -> None:
        self.bk.write_settings(DCLevel(self.PROGRAMMING_V, self.PROGRAMMING_I))

    def get_params(self) -> None:
        sheet = pd.read_excel(self.PARAMS_PATH, comment='#', sheet_name='params')
        rows = cast(List[Dict], sheet.to_dict('records'))
        rows.sort(key=itemgetter('row'))
        self.params = [messages.Param(**row) for row in rows]
        list(map(self.put, self.params))

    def __init__(self, to_view: ThreadConnection = None) -> None:
        self.q = to_view
        self.put = to_view.put if to_view is not None else self.info
        self.instrument_setup()
        self.set_power_supply_for_programming()
        self.bk.write_settings(output_state=False)
        self.masks = [1 << ch for ch in range(4)] + [15]
        self.string_results = list()
        self.params: List[messages.Param] = list()
        self.uid_table = dict()
        self.dut_id_table = dict()

    def pixie_ch_command(self, mask: int) -> None:
        self.ftdi.ser.send_ascii(f'p{mask}\n')

    def programming_message_adapter(self, msg) -> None:
        self.put(getattr(messages, type(msg).__name__)(**asdict(msg)))

    def program(self, fp: str) -> None:
        self.set_power_supply_for_programming()
        sleep(.1)
        self.ftdi.ser.send_ascii('U')
        sleep(self.AFTER_ERASE_WAIT_S)
        self.ftdi.dta_program_firmware(fp, self.programming_message_adapter)

    def string_check(self, param: messages.Param) -> None:
        self.bk.write_settings(DCLevel(param.v, param.i))
        [self.pixie_ch_command(param.ch_mask) for _ in range(20)]
        sleep(self.CH_SETTLE_WAIT_S)
        light = self.lm.measure()
        power = self.bk.measure()
        dist = light.distance_from(param)
        dist_pf = dist <= param.color_dist_max
        fcd_pf = (param.fcd_nom - param.fcd_tol) <= light.fcd <= (param.fcd_nom + param.fcd_tol)
        p_pf = (param.p_nom - param.p_tol) <= power.P <= (param.p_nom + param.p_tol)
        self.pixie_ch_command(0)
        result = messages.Result(param.row, light.x, light.y, dist, light.fcd, power.P, dist_pf, fcd_pf, p_pf)
        self.put(result)
        self.string_results.append(result)
        sleep(.1)

    def test(self, dut: messages.DUT) -> None:
        self.put(dut)
        self.bk.write_settings(output_state=True)
        sleep(self.AFTER_ERASE_WAIT_S)
        self.program(self.TESTING_FW_PATH)
        winsound.Beep(1500, 250)

        sleep(self.AFTER_ERASE_WAIT_S)
        self.put(messages.StringsStart())
        self.string_results.clear()
        [self.string_check(param) for param in self.params]
        test_pf = all(result.row_pf for result in self.string_results)

        with open(self.RESULT_PATH, 'a', newline='') as wf:
            writer = csv.DictWriter(wf, result_header)
            writer.writerows([dict(
                dut_id=dut.dut_id, t=datetime.now(), test_pf=test_pf, **asdict(result)
            ) for result in self.string_results])

        self.program(self.PRODUCTION_FW_PATH)
        self.bk.write_settings(output_state=False)
        for _ in range(2):
            winsound.Beep(1500, 250)
            sleep(.250)

        winsound.Beep(2500 if test_pf else 1000, 1000)

        self.dut_id_table[dut.dut_id] = dict(test_pf=test_pf, **asdict(dut))
        self.write_association_table()
        self.put(messages.TestResult(test_pf))

    # noinspection PyMethodMayBeStatic
    def nfc_present(self) -> bool:  # TODO:
        return self.nfc.is_present()

    # noinspection PyMethodMayBeStatic
    def get_uid(self) -> str:  # TODO:
        [self.nfc.interface.reset_input_buffer() for _ in range(5)]
        first = self.nfc.read_uid()
        if self.nfc.read_uid() == first and len(first) > 5:
            return first
        return ''

    def read_association_table(self) -> None:
        self.uid_table.clear()
        self.dut_id_table.clear()
        with open(self.ASSOCIATION_TABLE_PATH, newline='') as rf:
            for row in csv.DictReader(rf):
                row['dut_id'] = int(row['dut_id'])
                self.dut_id_table[row['dut_id']] = row
                self.uid_table[row['uid']] = row

    def write_association_table(self) -> None:
        with open(self.ASSOCIATION_TABLE_PATH, 'w+', newline='') as wf:
            writer = csv.DictWriter(wf, assoc_table_header)
            writer.writeheader()
            writer.writerows(list(self.dut_id_table.values()))

    # noinspection PyMethodMayBeStatic
    def get_dut_id(self, uid: str) -> int:  # TODO:
        self.read_association_table()
        if not self.uid_table:
            return 1
        row = self.uid_table.get(uid, None)
        if row is None:
            return max(self.dut_id_table.keys()) + 1
        return row['dut_id']

    def should_stop(self) -> bool:  # TODO:
        try:
            self.q.get_nowait()
        except queue.Empty:
            pass
        except (SentinelReceived, ConnectionClosed):
            return True

    def mainloop(self) -> None:
        try:
            self.get_params()
            while 1:
                if self.nfc_present():
                    uid = self.get_uid()
                    if uid:
                        winsound.Beep(1000, 500)
                        self.read_association_table()
                        self.test(messages.DUT(self.get_dut_id(uid), uid))

                if self.should_stop():
                    return self.q.put_sentinel()
        except Exception:
            self.q.put_sentinel()
            raise


class HackScript:
    progress: progressbar.ProgressBar

    def __init__(self):
        self.ftdi = RS485()
        self.ftdi.instrument_setup()

    def __call__(self, *args, **kwargs):
        raise NotImplementedError

    @classmethod
    def run(cls) -> None:
        logger.with_suppressed(cls())
