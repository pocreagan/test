from collections import namedtuple

__all__ = [
    'UnitData',
    'TestResult',
    'String_Measurement',
    'Thermal_Measurement',
]

UnitData = namedtuple('UnitData', ['timestamp', 'mn', 'sn', 'config'])
TestResult = namedtuple('Message', ['status'])
String_Measurement = namedtuple('String_Measurement', ['string_dmx', 'x', 'y', 'fcd', 'W'])
Thermal_Measurement = namedtuple('Thermal_Measurement', ['string_dmx', 'fcd'])
