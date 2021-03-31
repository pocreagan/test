from typing import Callable
from typing import Type

from src.base.actor import proxy
from src.base.log.mixin import Logged
from src.instruments.dc_power_supplies.connection_states import ConnectionStateCalcType
from src.instruments.dc_power_supplies.connection_states import ConnectionState
from src.instruments.dc_power_supplies import DCLevel


__all__ = [
    '_DCPowerSupply',
]

class DCKneeUpdate:
    pass


class _DCPowerSupply(Logged):
    def measure(self, fresh: bool = True) -> DCLevel:
        raise NotImplementedError

    def set_settings(self, dc_level: DCLevel) -> None:
        raise NotImplementedError

    def get_settings(self) -> DCLevel:
        raise NotImplementedError

    def set_output(self, output_state: bool) -> None:
        raise NotImplementedError

    def get_output(self) -> bool:
        raise NotImplementedError

    def write_settings(self, dc_level: DCLevel = None, output_state: bool = None) -> None:
        raise NotImplementedError

    def _on_setting_error(self, err_string: str) -> None:
        raise NotImplementedError

    def calculate_connection_state(self, calc: Type[ConnectionStateCalcType]) -> ConnectionState:
        self.write_settings(calc.power_supply_setting, True)
        state = calc.calculate(self.measure(fresh=True))
        self.info(state)
        return state

    def calculate_knee(self, percent_of_max: float, num_steps: int, top: float, bottom: float,
                       consumer: Callable[[DCKneeUpdate], None]) -> float:
        raise NotImplementedError

    def off(self) -> None:
        return self.write_settings(DCLevel(0., 0.), False)
