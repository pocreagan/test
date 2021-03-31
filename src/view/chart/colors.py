__all__ = [
    'STEP_PROGRESS_COLORS',
    'C',
    'CH_COLORS',
]

STEP_PROGRESS_COLORS = {
    'IN PROGRESS': '#0000ff',
    'PASS': '#00ff00',
    'FAIL': '#ff0000',
}


class C(object):
    _GRN = '#29bf12'
    _RED = '#ff0015'
    _BLU = '#390099'
    _LIM = '#d7f75b'
    _THR = '#dab6c4'
    _WTE = '#f3f3f3'

    @classmethod
    def _convert(cls, alpha) -> str:
        return str(hex(alpha)).split('x')[-1].zfill(2)

    @classmethod
    def red(cls, alpha: int) -> str:
        return cls._RED + cls._convert(alpha)

    @classmethod
    def grn(cls, alpha: int) -> str:
        return cls._GRN + cls._convert(alpha)

    @classmethod
    def blu(cls, alpha: int) -> str:
        return cls._BLU + cls._convert(alpha)

    @classmethod
    def lim(cls, alpha: int) -> str:
        return cls._LIM + cls._convert(alpha)

    @classmethod
    def thr(cls, alpha: int) -> str:
        return cls._THR + cls._convert(alpha)

    @classmethod
    def wte(cls, alpha: int) -> str:
        return cls._WTE + cls._convert(alpha)


CH_COLORS = {
    'T100': (C.thr(255), .010),
    'R100': (C.red(255), .010),
    'R050': (C.red(255), .0075),
    'G100': (C.grn(255), .010),
    'G050': (C.grn(255), .0075),
    'B100': (C.blu(255), .010),
    'B050': (C.blu(255), .0075),
    'L100': (C.lim(255), .010),
    'L050': (C.lim(255), .0075),
    'W100': (C.wte(255), .010),
}
