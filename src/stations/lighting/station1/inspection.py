from dataclasses import dataclass
from functools import partial
from itertools import starmap

import cv2
import numpy as np

ITERATIONS = 100
# ITERATIONS = 1

SAVE_DIR = 'pyspin'
ROI_PIX = 15
THRESHOLD = 50
CONTOUR_MIN_AREA = 1000
AOI_X0 = 200
AOI_X1 = 1088
AOI_Y0 = 0
AOI_Y1 = 888
HEIGHT = 964
WIDTH = 1288


@dataclass
class LED_Criteria:
    Rmin: float
    Rmax: float
    Gmin: float
    Gmax: float
    Bmin: float
    Bmax: float
    Amin: float
    Amax: float


@dataclass
class LED_Object:
    r: float = 0.0
    g: float = 0.0
    b: float = 0.0
    area: float = 0.0
    y0: int = 0
    y1: int = 0
    x0: int = 0
    x1: int = 0


def analyze(contour, color, grey, roi_px, criterion):
    led = LED_Object()
    M = cv2.moments(contour)

    led.area = M['m00']

    y, x = [int(M[k] / led.area) for k in ['m01', 'm10']]
    y0, y1, x0, x1 = y - roi_px, y + roi_px, x - roi_px, x + roi_px
    roi_x, roi_y, w, h = cv2.boundingRect(contour)

    roi_x0, roi_x1, roi_y0, roi_y1 = roi_x, roi_x + w, roi_y, roi_y + h

    if (y0 < roi_y0) or (y1 > roi_y1) or (x0 < roi_x0) or (x1 > roi_x1):
        return None

    roi = color[y0:y1, x0:x1]
    roi_dy, roi_dx = y0 - roi_y0, x0 - roi_x0

    alpha = grey[roi_y0:roi_y1, roi_x0:roi_x1]

    average = roi.mean(axis=0).mean(axis=0)
    led.b, led.g, led.r = average / np.sum(average)

    print(led.r, led.g, led.b, led.area)

    if not (criterion.Amin <= led.area <= criterion.Amax):
        return None
    if not (criterion.Rmin <= led.r <= criterion.Rmax):
        return None
    if not (criterion.Gmin <= led.g <= criterion.Gmax):
        return None
    if not (criterion.Bmin <= led.b <= criterion.Bmax):
        return None

    led_img = np.stack((alpha,) * 3, axis=-1)
    led_img[roi_dy:roi_dy + roi.shape[0], roi_dx:roi_dx + roi.shape[1]] = roi
    led_img = np.dstack((led_img, alpha))
    led.y0, led.y1, led.x0, led.x1 = roi_y0, roi_y0 + \
                                     led_img.shape[0], roi_x0, roi_x0 + led_img.shape[1]

    return led, (led.y0, led.y1, led.x0, led.x1), led_img


def edges(i, tup):
    if i % 2:
        return max(tup)
    return min(tup)


def inspect(color, new_img, criterion):
    color = color[AOI_Y0: AOI_Y1, AOI_X0: AOI_X1]

    grey = cv2.cvtColor(color, cv2.COLOR_BGR2GRAY)
    grey = cv2.threshold(grey, THRESHOLD, 255, cv2.THRESH_BINARY)[-1]
    contours = cv2.findContours(grey, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)[0]

    results = list(
        filter(
            lambda x: not x is None,
            map(
                partial(
                    analyze,
                    color=color,
                    grey=grey,
                    roi_px=ROI_PIX,
                    crit=criterion
                ), filter(
                    lambda x: cv2.contourArea(x) > CONTOUR_MIN_AREA,
                    contours
                )
            )
        )
    )

    if len(results) > 0:
        leds, rois, imgs = zip(*results)
        for led, img in zip(leds, imgs):
            new_img[led.y0:led.y1, led.x0:led.x1] = img

        y0s, y1s, x0s, x1s = starmap(edges, enumerate(zip(*rois)))
        xsize, ysize, xpad, ypad = x1s - x0s, y1s - y0s, 0, 0
        if xsize > ysize:
            ypad = (xsize - ysize) // 2
        else:
            xpad = (ysize - xsize) // 2
        new_img = new_img[y0s - ypad:y1s + ypad, x0s - xpad:x1s + xpad]

        return new_img, leds

    return grey, []


TEMPLATE = np.zeros((AOI_Y1 - AOI_Y0, AOI_X1 - AOI_X0, 4), dtype=np.uint8)
CRITERION_OLD = LED_Criteria(
    Rmin=0.0,
    Rmax=0.5,
    Gmin=0.6,
    Gmax=1.0,
    Bmin=0.0,
    Bmax=0.5,
    Amin=6000,
    Amax=8000,
)
CRITERION_BLU = LED_Criteria(
    Rmin=0.6,
    Rmax=1.,
    Gmin=0.,
    Gmax=0.35,
    Bmin=0.0,
    Bmax=0.2,
    Amin=60,
    Amax=80000,
)
CRITERION_RED = LED_Criteria(
    Rmin=0.,
    Rmax=0.2,
    Gmin=0.,
    Gmax=0.5,
    Bmin=0.4,
    Bmax=1.,
    Amin=60,
    Amax=80000,
)
CRITERION_LIM = LED_Criteria(
    Rmin=0.2,
    Rmax=0.6,
    Gmin=0.35,
    Gmax=0.6,
    Bmin=0.,
    Bmax=0.3,
    Amin=60,
    Amax=80000,
)
CRITERION_GRN = LED_Criteria(
    Rmin=0.,
    Rmax=0.5,
    Gmin=0.5,
    Gmax=1.,
    Bmin=0.,
    Bmax=0.4,
    Amin=60,
    Amax=80000,
)

if __name__ == '__main__':
    pass
