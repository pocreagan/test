from src.instruments.wet.nfc import NFC
from src.instruments.testers.leak_tester import LeakTester
from src.base.log import logger

log = logger(__name__)


def do():
    lt = LeakTester()
    lt.instrument_setup()
    lt = lt.proxy_spawn()

    nfc = NFC()
    nfc.instrument_setup()
    nfc = nfc.proxy_spawn()

    nfc_promise = nfc.test()
    lt_promise = lt.get_test_from_model_number(897, log.info)
    lt_promise.resolve()
    lt_promise = lt.run_test_from_model_number(897, log.info)

    nfc_promise.resolve()
    lt_promise.resolve()

    nfc = nfc.proxy_join()
    lt = lt.proxy_join()


if __name__ == '__main__':
    with logger:
        do()
        # visa_test()
