from enum import auto
from enum import Enum

__all__ = [
    'SubscribeTo',
]


class SubscribeTo(Enum):
    VIEW = auto()
    STATION = auto()
