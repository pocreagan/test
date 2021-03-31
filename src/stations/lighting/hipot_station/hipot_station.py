# from src.instruments.testers.hipot_tester import HipotTester
from src.instruments.dc_power_supplies.lambda_ps import LambdaPowerSupply
from src.base.log import logger

log = logger(__name__)


def do():
    lt = LambdaPowerSupply()
    lt.instrument_setup()
    lt = lt.proxy_spawn()

    # hip = HipotTester()
    # hip.instrument_setup()
    # hip = hip.proxy_spawn()

    # hip_promise = hip.run_test_by_number(2)
    lt_promise = lt.test()
    # hip_promise.resolve()
    lt_promise.resolve()

    # hip.proxy_join()
    lt.proxy_join()


if __name__ == '__main__':
    with logger:
        do()
