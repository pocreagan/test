from dataclasses import dataclass
from dataclasses import fields
from typing import Dict


@dataclass
class FirmwareSetup:
    version: int
    n: int


@dataclass
class FirmwareIncrement:
    i: int


@dataclass
class DUT:
    dut_id: int
    uid: str

    def update_view(self, widget) -> None:
        for k in fields(self):
            getattr(widget, k.name).set(str(getattr(self, k.name)))


@dataclass
class DUTLabel:
    dut_id: int


@dataclass
class ShipmentLabel:
    shipment_id: int


@dataclass
class TestResult:
    test_pf: bool


class StringsStart:
    pass


@dataclass
class Param:
    row: int
    name: str
    v: float
    i: float
    ch_mask: int
    x: float
    y: float
    color_dist_max: float
    fcd_nom: float
    fcd_tol: float
    p_nom: float
    p_tol: float

    def for_view(self) -> Dict[str, str]:
        return dict(
            name=self.name,
            color=f'{self.color_dist_max:.4f}max from ({self.x:.4f}, {self.y:.4f})',
            brightness=f'{self.fcd_nom - self.fcd_tol:.1f} < fcd < {self.fcd_nom + self.fcd_tol:.1f}',
            power=f'{self.p_nom - self.p_tol:.1f} < W < {self.p_nom + self.p_tol:.1f}',
        )

    def update_view(self, row) -> None:
        for k, v in self.for_view().items():
            getattr(row, f'{k}_param').set(v)


@dataclass
class Result:
    row: int
    x: float
    y: float
    dist: float
    fcd: float
    p: float
    dist_pf: bool
    fcd_pf: bool
    p_pf: bool
    row_pf: bool = None

    def __post_init__(self):
        self.row_pf = self.dist_pf and self.fcd_pf and self.p_pf

    def update_view(self, row) -> None:
        row.color_result.set(f'({self.x:.4f}, {self.y:.4f})')
        row.color_dist_result.set(f'{self.dist:.4f}')
        row.color_dist_result_label['fg'] = 'green' if self.dist_pf else 'red'
        row.brightness_result.set(f'{self.fcd:.1f}')
        row.brightness_result_label['fg'] = 'green' if self.fcd_pf else 'red'
        row.power_result.set(f'{self.p:.1f}')
        row.power_result_label['fg'] = 'green' if self.p_pf else 'red'
        row.row_result.set('PASS' if self.row_pf else 'FAIL')
        row.row_result_label['fg'] = 'green' if self.row_pf else 'red'

