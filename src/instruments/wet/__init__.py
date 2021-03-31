from pathlib import Path
from typing import Dict
from typing import List
from typing import Tuple
from typing import Union

__all__ = [
    'CFG_T',
    'DTA_T',
    'FP_T',
]

CFG_T = Dict[Tuple[int, int], int]
DTA_T = List[bytes]
FP_T = Union[Path, str]
