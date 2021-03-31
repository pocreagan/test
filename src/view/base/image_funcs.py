import tempfile
from pathlib import Path

from framework.base.log import logger
from framework.model import APP

# import cv2
# import numpy as np
# from reportlab.graphics import renderPM
# from svglib.svglib import svg2rlg
# from PIL import Image
__all__ = [
    'make_black_background_transparent',
    'svg_to_png',
    'make_temporary_transparent_icon',
    'make_circle_glyph',
]

log = logger(__name__)


def make_circle_glyph(size, rel_radius: float, color_rgb: tuple[int, ...]):
    fp = APP.R.img(f'glyph-{"-".join(map(str, [size, *color_rgb]))}.png')
    if not APP.R.img(fp).exists():
        import cv2
        import numpy as np
        from PIL import Image

        half = int(size / 2.)
        color = color_rgb[::-1]
        img = np.zeros((size, size, 3), dtype=np.uint8)
        img = cv2.circle(img, center=(half, half), radius=int((size * rel_radius) / 2), color=color,
                         thickness=-1)
        grey_original = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        _, grey = cv2.threshold(grey_original, 1, 255, cv2.THRESH_BINARY)
        alpha = cv2.bitwise_or(grey, np.zeros((*img.shape[:-1], 1), dtype=np.uint8))
        cv2.imwrite(str(fp), np.dstack((img, alpha)))
    return fp


def make_black_background_transparent(fp: str) -> None:
    import cv2
    import numpy as np

    img = cv2.imread(fp, cv2.IMREAD_COLOR)
    grey_original = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, grey = cv2.threshold(grey_original, 1, 255, cv2.THRESH_BINARY)
    alpha = cv2.bitwise_or(grey, np.zeros((*img.shape[:-1], 1), dtype=np.uint8))
    cv2.imwrite(fp, np.dstack((img, alpha)))


def svg_to_png(filename: str) -> Path:
    destination: Path = APP.R._img(filename + '.png')
    if not destination.exists():
        log.debug(f'creating transparent .png from {filename}...')
        dest_string = str(destination)
        source = APP.R._img(filename + '.svg')

        from reportlab.graphics import renderPM
        from svglib.svglib import svg2rlg

        renderPM.drawToFile(svg2rlg(str(source)), dest_string, fmt="PNG", bg=0x000000)
        make_black_background_transparent(dest_string)
        log.debug(f'done creating transparent .png from {filename}.')
    return destination


def make_square(img, min_size=256, fill_color=(0, 0, 0, 0)):
    x, y = img.size
    size = max(min_size, x, y)

    from PIL import Image

    new_im = Image.new('RGBA', (size, size), fill_color)
    new_im.paste(img, (int((size - x) / 2), int((size - y) / 2)))
    return new_im


def make_ico(img, filename: str, sizes: tuple[int, ...]):
    img.save(str(APP.R._img(filename + '.ico')), sizes=[(v, v) for v in sizes])


def make_icon(sizes: tuple[int, ...] = (255,)):
    from PIL import Image

    make_ico(make_square(Image.open(svg_to_png('wet_logo'))), 'wet_logo', sizes)


def make_temporary_transparent_icon() -> str:
    icon_path = tempfile.mkstemp()[1]
    with open(icon_path, 'wb') as f:
        f.write((b'\x00\x00\x01\x00\x01\x00\x10\x10\x00\x00\x01\x00\x08\x00h\x05\x00\x00'
                 b'\x16\x00\x00\x00(\x00\x00\x00\x10\x00\x00\x00 \x00\x00\x00\x01\x00'
                 b'\x08\x00\x00\x00\x00\x00@\x05\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00'
                 b'\x00\x01\x00\x00\x00\x01') + b'\x00' * 1282 + b'\xff' * 64)
    log.debug(f'made temporary transparent window icon')
    return icon_path


if __name__ == '__main__':
    make_circle_glyph(150, .75, (25, 135, 25))
