import cv2
import numpy as np
from numpy import round as npround
from time import perf_counter
from PIL import ImageFont, ImageDraw, Image, ImageOps
from datetime import datetime, timedelta

SAVE_DIR = 'pyspin'
ROI_PIX = 15
RED = (0, 0, 255)
GRN = (0, 255, 0)
BLK = (0, 0, 0)
WTE = (255, 255, 255)
PIL_GRN = tuple(reversed(GRN))
PIL_RED = tuple(reversed(RED))

PARAM_LABELS = [
    'Vin',
    'Iin',
    'Pin',
    'Hipot',
    'Knee',
]
PARAM_UNITS = [
    'V',
    'A',
    'W',
    'V',
    'V',
]
META_LABELS = [
    'MN: ',
    'SN: ',
    'String: ',
    'Date: ',
    'Time: ',
]
PARAM_COL_OFF_X = [
    0,
    90,
    110,
    70,
    30,
    60,
]

font = cv2.FONT_HERSHEY_SIMPLEX
font_scale = 0.4
PADDING = 150
IMG_DIMS = 375

CROSS_SIZE = 25
LED_FONT_SIZE = 20
PARAMS_FONT_SIZE = 30
LED_OFF_X = 2
LOGO_OFF_X = 20
LOGO_OFF_Y = 20
TOP_PAD = 0
RIGHT_PAD = 300
PARAM_OFF_X = 390
led_font = ImageFont.truetype("LinotypeUnivers-430Regular.ttf", LED_FONT_SIZE)
params_font = ImageFont.truetype(
    "LinotypeUnivers-430Regular.ttf", PARAMS_FONT_SIZE)
PASS_FAIL_FONT = ImageFont.truetype("LinotypeUnivers-430Regular.ttf", 125)
UNIT_FONT = ImageFont.truetype("LinotypeUnivers-430Regular.ttf", 50)
logo = Image.open('logo.jpg')


def inspect(img, params, metadata, unit):
    ti = perf_counter()
    *thresholds, n, string = params
    (area_min, area_max), *color_thresh = thresholds
    test_data = [f'{k}: {list(th)}' for k, th in zip('ARGB', thresholds)]
    passing, annotations, boxes = True, [], []
    x_c, y_c = 0, 0
    color = img[100:764, 200:1088]
    # color = img
    mask = np.zeros((*color.shape[:-1], 1), dtype=color.dtype)

    grey_original = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
    _, grey = cv2.threshold(grey_original, 50, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(
        grey, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    d_date, d_time = str(datetime.now()).split('.')[0].split(' ')
    unit_info = (unit[0], unit[1], string)
    timestamp = f'D:{d_date.replace("-", "")}  T:{d_time.replace(":", "")}'

    num_leds = len(contours)
    if num_leds < n:
        passing = False

    for contour in contours:
        obj_passing = True

        M = cv2.moments(contour)
        area = M['m00']

        x, y = [int(M[k] / area) for k in ['m01', 'm10']]
        x_c += x
        y_c += y

        x0, x1, y0, y1 = x - ROI_PIX, x + ROI_PIX, y - ROI_PIX, y + ROI_PIX
        external_poly = np.array(
            [[[y0, x0], [y1, x0], [y1, x1], [y0, x1]]], dtype=np.int32)
        cv2.fillPoly(mask, external_poly, WTE)

        square = color[x0:x1, y0:y1]
        average = square.mean(axis=0).mean(axis=0)
        total = np.sum(average)
        values = [v / total for v in average]

        annos = []

        area_color = PIL_GRN
        if not (area_min <= area <= area_max):
            area_color = PIL_RED
            obj_passing = False
        annos.append((f'{round(area)}', area_color))

        for v, (low, high) in zip(values, color_thresh):
            color_color = PIL_GRN
            if not (low <= v <= high):
                color_color = PIL_RED
                obj_passing = False
        s = [f'{str(round(v, 3))[1:]}' for k, v in zip('RGB', values)]
        s = '\n'.join(s)
        annos.append((s, color_color))

        box_color = PIL_GRN
        if not obj_passing:
            box_color = PIL_RED
            passing = False

        x, y, w, h = cv2.boundingRect(contour)

        annotations.append((annos, (x + w, y)))
        boxes.append((((x, y), (x + w, y + h)), box_color))

    tf = perf_counter()
    test_data.append(f'Δt: {round((tf - ti) * 1000)}ms')

    mask_inv = cv2.bitwise_not(mask)
    masked_color = cv2.bitwise_and(color, color, mask=mask)
    masked_grey = cv2.bitwise_and(grey_original, grey_original, mask=mask_inv)
    masked_grey = np.stack((masked_grey,) * 3, axis=-1)
    result = masked_color + masked_grey

    x_c, y_c = int(y_c / num_leds), int(x_c / num_leds)
    cv2.line(result, (x_c - CROSS_SIZE, y_c), (x_c + CROSS_SIZE, y_c), WTE, 1)
    cv2.line(result, (x_c, y_c - CROSS_SIZE), (x_c, y_c + CROSS_SIZE), WTE, 1)

    for (co0, co1), c in boxes:
        cv2.rectangle(result, co0, co1, c, 1)
    result = cv2.copyMakeBorder(
        result, PADDING, PADDING, PADDING, PADDING, cv2.BORDER_CONSTANT, value=BLK)
    nx_c, ny_c = y_c + PADDING, x_c + PADDING
    x0, x1, y0, y1 = nx_c - IMG_DIMS, nx_c + IMG_DIMS, ny_c - IMG_DIMS, ny_c + IMG_DIMS
    result = result[x0:x1, y0:y1]

    cy, cx, _ = [v // 2 for v in result.shape]
    dy, dx = y_c - cx, x_c - cy

    result = Image.fromarray(result)
    draw = ImageDraw.Draw(result)

    for annos, (startx, starty) in annotations:
        for i, (s, c) in enumerate(annos):
            draw.text(((startx + LED_OFF_X) - dx, (starty + ((i + 1) * LED_FONT_SIZE) -
                                                   LED_FONT_SIZE) - dy), s, font=led_font, fill=c)

    result = ImageOps.expand(result, (0, TOP_PAD, RIGHT_PAD, 0))
    draw = ImageDraw.Draw(result)
    width, height = result.size

    startx = (width - PARAM_OFF_X) - LOGO_OFF_X
    starty = LOGO_OFF_Y

    # metadata_new = (('LEDs',(f'{num_leds}/{n}', None), num_leds == n),) + metadata
    for i, (label, unit, (v, (nom, tol), p_f)) in enumerate(zip(PARAM_LABELS, PARAM_UNITS, metadata)):
        offset = 0
        for s, off in zip([label, v, nom, '±', tol, unit], PARAM_COL_OFF_X):
            offset += off
            draw.text((startx + offset, (starty + ((PARAMS_FONT_SIZE + 2) * i))),
                      str(s), font=params_font, fill=PIL_GRN if p_f else PIL_RED)

    big_p_f = ('PASS', PIL_GRN)
    if any([not v[-1] for v in metadata]) or (not passing):
        big_p_f = ('  FAIL', PIL_RED)

    big_w, big_h = draw.textsize(big_p_f[0], font=PASS_FAIL_FONT)
    big_pf_x = (width - big_w) - LOGO_OFF_X
    draw.text((big_pf_x, (height - big_h) - LOGO_OFF_Y),
              big_p_f[0], font=PASS_FAIL_FONT, fill=big_p_f[1])

    time_w, time_h = draw.textsize(timestamp, font=params_font)
    time_co = (LOGO_OFF_X, (height - time_h) - LOGO_OFF_Y)
    draw.text(time_co, timestamp, font=params_font, fill=WTE)

    startx = big_pf_x
    endx = width - LOGO_OFF_X
    starty_unit = (height - (PASS_FAIL_FONT.size + LOGO_OFF_Y)) - 30
    for i, (label, s) in enumerate(reversed(list(zip(META_LABELS, unit_info)))):
        draw.text((startx, starty_unit - (i * (UNIT_FONT.size + 10))),
                  label, font=UNIT_FONT, fill=WTE)
        draw.text((endx - draw.textsize(s, font=UNIT_FONT)[0], starty_unit - (i * (UNIT_FONT.size + 10))),
                  s, font=UNIT_FONT, fill=WTE)

    starty_inspect = (height - (params_font.size + LOGO_OFF_Y)) - 30
    for i, s in enumerate(reversed(list(test_data))):
        draw.text((LOGO_OFF_X, starty_inspect - (i * (led_font.size + 5))),
                  s, font=led_font, fill=WTE)

    fill, y = PIL_GRN if num_leds == n else PIL_RED, starty + ((PARAMS_FONT_SIZE + 2) * len(PARAM_LABELS))
    s = f'{num_leds} / {n} LEDs'
    draw.text((endx - draw.textsize(s, font=params_font)[0], y),
              s, font=params_font, fill=fill)

    result.paste(logo, (LOGO_OFF_X, LOGO_OFF_Y))

    return result, passing


if __name__ == '__main__':
    src_path = r'C:\light_line\dev\images\PolyDragon String 0 SN 1 32V 250mA.jpg'
    dst_path = r'C:\light_line\bin\img.jpg'
    img = cv2.imread(src_path, cv2.IMREAD_COLOR)
    n = 18
    params = (
        (3000, 4000),
        (0., 0.5),
        (0.6, 1.),
        (0., 0.5),
        18,
        'Lime'
    )
    metadata = (
        (32.00, (32, 0.1), True),
        (3.29, (3.5, 0.5), True),
        (105.41, (98.2, 16), True),
        (6.08, (5.3, 1), True),
        (23.00, (23, 2), True),
    )
    unit = (
        '10-00938',
        '12345678',
    )
    ti = perf_counter()
    result, passing = inspect(img, params, metadata, unit)
    tf = perf_counter()
    print(tf - ti)
    result.show("new image")
