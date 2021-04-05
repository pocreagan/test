from dataclasses import dataclass
from datetime import datetime
from enum import auto
from enum import Enum
from typing import List

__all__ = [
    'ScanMessage',
    'GetFullHistoryMessage',
    'StationMode',
    'ModeChangeMessage',
    'TECheckMessage',
    'InstructionMessage',
    'OneHistoryMessage',
    'FullHistoryMessage',
]


@dataclass
class ScanMessage:
    scan_string: str


@dataclass
class GetFullHistoryMessage:
    pass


@dataclass
class OneHistoryMessage:
    id: int
    pf: bool
    dt: datetime
    mn: str
    sn: str


@dataclass
class FullHistoryMessage:
    records: List[OneHistoryMessage]


class StationMode(Enum):
    REWORK: auto()
    TESTING: auto()


@dataclass
class ModeChangeMessage:
    mode: StationMode


@dataclass
class TECheckMessage:
    pass


@dataclass
class InstructionMessage:
    major: str
    minor: str


@dataclass
class StepsInit:
    steps: List[str]


@dataclass
class StepSubtext:
    step: str
    subtext: str
    value: float = None


@dataclass
class StepStatus:
    step: str
