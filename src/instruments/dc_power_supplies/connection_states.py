from enum import auto
from enum import Enum

from src.instruments.dc_power_supplies import DCLevel

__all__ = [
    'ConnectionStateCalcType',
    'LightLineV1ConnectionState',
]


class ConnectionState(Enum):
    UNCONNECTED = auto()
    CONNECTED = auto()
    FAULT_SHORT_CIRCUIT = auto()
    FAULT_REVERSED_POLARITY = auto()
    FAULT_POWER_SUPPLY_ERROR = auto()

    def __bool__(self) -> bool:
        return self == type(self).CONNECTED


class ConnectionStateCalcType:
    power_supply_setting: DCLevel

    @classmethod
    def calculate(cls, meas: DCLevel) -> ConnectionState:
        raise NotImplementedError


class LightLineV1ConnectionState(ConnectionStateCalcType):
    power_supply_setting = DCLevel(10, .5)

    @classmethod
    def calculate(cls, meas: DCLevel) -> 'ConnectionState':
        if meas.V > 9.:
            if meas.A < .015:
                return ConnectionState.UNCONNECTED
            return ConnectionState.CONNECTED
        elif meas.A > .45:
            if meas.V < 2.:
                if meas.V < .3:
                    return ConnectionState.FAULT_SHORT_CIRCUIT
                return ConnectionState.FAULT_REVERSED_POLARITY
            return ConnectionState.CONNECTED
        return ConnectionState.FAULT_POWER_SUPPLY_ERROR
