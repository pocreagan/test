import functools

from matplotlib.font_manager import FontProperties

__all__ = [
    'normal',
    'bold',
]

FONT_NAME = r'C:\Projects\test_framework\src\framework\model\resources\font\LinotypeUnivers-430Regular.ttf'

MULTIPLIER = 1.


def make_make_font(fp: str, weight: str = 'normal'):
    @functools.lru_cache(maxsize=None)
    def make_font(size: int) -> FontProperties:
        kwargs = dict(fname=fp, size=float(size) * MULTIPLIER, weight=weight)
        return FontProperties(**kwargs)

    return make_font


normal = make_make_font(FONT_NAME, 'normal')
bold = make_make_font(FONT_NAME, 'bold')
