from dataclasses import dataclass
from datetime import datetime
from enum import auto
from enum import Enum
from typing import List
from typing import Optional
from typing import Union

__all__ = [
    'ScanMessage',
    'StationMode',
    'ModeChangeMessage',
    'TECheckMessage',
    'InstructionMessage',
    'NotificationMessage',
    'HistoryGetAllMessage',
    'HistoryAddEntryMessage',
    'HistorySetAllMessage',
    'HistorySelectEntryMessage',
    'StepsInitMessage',
    'StepStartMessage',
    'StepMinorTextMessage',
    'StepProgressMessage',
    'StepFinishMessage',
    'GetMetricsMessage',
    'MetricsMessage',
]


@dataclass
class ScanMessage:
    scan_string: str


class StationMode(Enum):
    REWORK = auto()
    TESTING = auto()


@dataclass
class ModeChangeMessage:
    mode: StationMode


@dataclass
class TECheckMessage:
    pass


@dataclass
class GetMetricsMessage:
    pass


@dataclass
class MetricsMessage:
    pass_hour: int
    fail_hour: int
    pass_day: int
    fail_day: int


@dataclass
class InstructionMessage:
    major: str
    minor: str
    color: Optional[str] = None


@dataclass
class NotificationMessage:
    major: str
    minor: str
    color: Optional[str] = None


@dataclass
class StepsInitMessage:
    steps: List[str]


@dataclass
class StepStartMessage:
    step: str
    minor_text: Optional[str] = None
    max_val: Optional[Union[int, float]] = None


@dataclass
class StepMinorTextMessage:
    step: str
    minor_text: str


@dataclass
class StepProgressMessage:
    step: str
    value: Union[int, float]


@dataclass
class StepFinishMessage:
    step: str
    success: Optional[bool]


@dataclass
class HistoryGetAllMessage:
    pass


@dataclass
class HistoryAddEntryMessage:
    id: int
    pf: bool
    dt: datetime
    mn: str
    sn: str


@dataclass
class HistorySetAllMessage:
    records: List[HistoryAddEntryMessage]


@dataclass
class HistorySelectEntryMessage:
    id_: int
