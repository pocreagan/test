from dataclasses import dataclass
from dataclasses import fields
from typing import Dict
from typing import Tuple


__all__ = [
    'DCLevel',
    'DCRamp',
    'bk_ps',
    'lambda_ps',
]


@dataclass
class DCLevel:
    V: float
    A: float
    P: float = None  # type: ignore

    def __post_init__(self) -> None:
        self.P = self.V * self.A

    @property
    def tuple(self) -> Tuple[float, float]:
        return self.V, self.A

    def __eq__(self, o: 'DCLevel') -> bool:
        return self.V == o.V and self.A == o.A

    def as_dict(self) -> Dict[str, float]:
        return {k.name: getattr(self, k.name) for k in fields(self)}


class DCRamp:
    pass
