import csv
import logging
import re
from time import sleep

from progressbar import progressbar

from model import configuration
from src.base.log import logger
from src.stations.lighting.pixie_hack import HackScript
from src.stations.test_station import TestInstrument
from src.instruments.dc_power_supplies.bk_ps import BKPowerSupply
from src.instruments.light_meter import LightMeter
from src.instruments.wet.nfc import NFC
from src.instruments.wet.rs485 import RS485

log = logger(__name__)


class Assure(HackScript):
    bk = TestInstrument(BKPowerSupply(), logging.INFO)
    lm = TestInstrument(LightMeter(), logging.INFO)
    ftdi = TestInstrument(RS485(), logging.DEBUG)
    nfc = TestInstrument(NFC(), logging.INFO)

    _config = configuration.from_yml('pixie_hack/.yml')
    ASSOCIATION_TABLE_PATH = _config.field(str)
    SHIPMENT_ASSOCIATION_TABLE_PATH = _config.field(str)
    AFTER_ERASE_WAIT_S = _config.field(float)

    psu_label_pattern = re.compile(r'(?i)\[PSU#\|WDPB:001-(\d{4})]')
    dut_label_pattern = re.compile(r'(?i)\[PIXIE2PT0:(\d{4})]')

    def __init__(self):
        super().__init__()
        self.AFTER_ERASE_WAIT_S = int(self.AFTER_ERASE_WAIT_S)
        self.num_steps = int(self.AFTER_ERASE_WAIT_S * 10)

    def get_result_from_id(self, dut_id: int) -> bool:
        with open(self.ASSOCIATION_TABLE_PATH, newline='') as rf:
            return {int(row['dut_id']): row['test_pf'].upper() == 'TRUE' for row in csv.DictReader(rf)}.get(dut_id, None)

    def associate_id_with_shipment_label(self, dut_id: int) -> int:
        with open(self.SHIPMENT_ASSOCIATION_TABLE_PATH, newline='') as rf:
            table = {int(row['dut_id']): int(row['shipment_id']) for row in csv.DictReader(rf)}
        shipment_id = table.get(dut_id, None)
        if shipment_id is not None:
            return shipment_id
        if not table:
            table[dut_id] = 1
        else:
            table[dut_id] = max(table.values()) + 1
        with open(self.SHIPMENT_ASSOCIATION_TABLE_PATH, 'w+', newline='') as wf:
            writer = csv.DictWriter(wf, ['dut_id', 'shipment_id'])
            writer.writeheader()
            writer.writerows([dict(dut_id=k, shipment_id=v) for k, v in table.items()])
        return table[dut_id]

    def __call__(self) -> None:
        try:
            while 1:
                user_input = input('scan white DUT label -> ')
                parsed = self.dut_label_pattern.findall(user_input)
                if not parsed:
                    print('scan invalid')
                    continue
                dut_id = int(parsed[0])
                if not self.get_result_from_id(dut_id):
                    print(f'DUT #{dut_id} did not pass the light test.')
                    continue

                shipment_id = self.associate_id_with_shipment_label(dut_id)
                user_input = input(f'apply power to light, then scan black PSU label #{shipment_id} -> ')
                if user_input.upper() != f'[PSU#|WDPB:001-{shipment_id:04d}]':
                    print('scan invalid')
                    continue

                print('\nwaiting for startup...\n')
                self.progress = progressbar.ProgressBar(maxval=self.num_steps)
                self.progress.start()
                for i in range(1, self.num_steps + 1):
                    sleep(.1)
                    self.progress.update(i)
                print()

                print('\nerasing test firmware...\n')
                self.progress = progressbar.ProgressBar(maxval=5)
                self.progress.start()
                for i in range(1, 6):
                    self.ftdi.ser.send_ascii('U')
                    sleep(1.)
                    self.progress.update(i)
                print()

                print(f'\nwhite #{dut_id} / black #{shipment_id} done.\n')

        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    Assure.run()
