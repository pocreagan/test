from datetime import datetime
from itertools import chain

from numpy import linspace
from numpy.random import uniform

from lighting.LL3.chart.messages import *

__all__ = [
    'FakeData',
]

fake_params = {
    938: {
        'T100': {
            'color_point': {
                'x_nom': 0.312,
                'y_nom': 0.278,
                'dist': 0.058,
            },
            'fcd': {
                'nom': 730,
                'tol': 61,
            },
            'P': {
                'nom': 323,
                'tol': 16.1,
            },
            'thermal': {
                'dt': 10,
                'max_pct': 2.46,
            },
        }, 'L100': {
            'color_point': {
                'x_nom': 0.422,
                'y_nom': 0.544,
                'dist': 0.012,
            },
            'fcd': {
                'nom': 349,
                'tol': 42,
            },
            'P': {
                'nom': 98,
                'tol': 10.4,
            },
            'thermal': {
                'dt': 2,
                'max_pct': 1.15,
            },
        }, 'R100': {
            'color_point': {
                'x_nom': 0.69,
                'y_nom': 0.304,
                'dist': 0.012,
            },
            'fcd': {
                'nom': 137,
                'tol': 20,
            },
            'P': {
                'nom': 52.8,
                'tol': 5.75,
            },
            'thermal': {
                'dt': 2,
                'max_pct': 1.14,
            },
        }, 'G100': {
            'color_point': {
                'x_nom': 0.184,
                'y_nom': 0.715,
                'dist': 0.064,
            },
            'fcd': {
                'nom': 219,
                'tol': 34,
            },
            'P': {
                'nom': 88,
                'tol': 4.1,
            },
            'thermal': {
                'dt': 2,
                'max_pct': 0.79,
            },
        }, 'B100': {
            'color_point': {
                'x_nom': 0.155,
                'y_nom': 0.026,
                'dist': 0.015,
            },
            'fcd': {
                'nom': 32,
                'tol': 7,
            },
            'P': {
                'nom': 76,
                'tol': 5,
            },
            'thermal': {
                'dt': 2,
                'max_pct': 1.77,
            },
        }
    },
    897: {
        'W100': {
            'color_point': {
                'x_nom': 0.4152685,
                'y_nom': 0.3986709,
                'dist': 0.019576023,
            },
            'fcd': {
                'nom': 875,
                'tol': 50,
            },
            'P': {
                'nom': 109.1127273,
                'tol': 5,
            },
            'thermal': {
                'dt': 10,
                'max_pct': 3,
            },
        },
    }
}

fake_unit_data = {
    897: UnitData(timestamp=datetime.now(), sn='12345678', mn='10-00897',
                  config=[]),
    938: UnitData(timestamp=datetime.now(), sn='12345678', mn='10-00938',
                  config=['v2932', '00938 Initial', '00938 Final'])
}

fake_measurements = {
    938: [
        String_Measurement(
            string_dmx='T100',
            x=0.309835,
            y=0.274363,
            fcd=755.86084,
            W=325.898,
        ),
        String_Measurement(
            string_dmx='L100',
            x=0.419617,
            y=0.544854,
            fcd=368.183807,
            W=98.0799,
        ),
        String_Measurement(
            string_dmx='R100',
            x=0.688694,
            y=0.304241,
            fcd=142.425919,
            W=52.308,
        ),
        String_Measurement(
            string_dmx='G100',
            x=0.177422,
            y=0.715186,
            fcd=220.857132,
            W=87.3653,
        ),
        String_Measurement(
            string_dmx='B100',
            x=0.155717,
            y=0.024509,
            fcd=32.569885,
            W=77.1557,
        ),
    ], 897: [
        String_Measurement(
            string_dmx='W100',
            x=0.414364,
            y=0.399424,
            fcd=904.883606,
            W=110.642,
        ),
    ]
}

failure_chance = 0.3


def make_measurements(mn: int) -> list:
    thermals_list = []
    for (k, d), string_meas in zip(fake_params[mn].items(), fake_measurements[mn]):
        thermal_list = [string_meas]
        length_s = d['thermal']['dt']
        dts = linspace(0, length_s, length_s * 10)
        initial_val = string_meas.fcd
        drops = linspace(0, initial_val * (-(d['thermal']['max_pct'] / 100)), length_s * 10)
        randoms = uniform(0 + failure_chance, 1 + failure_chance, length_s * 10)

        for dt, drop, rand in zip(dts, drops, randoms):
            thermal_list.append(Thermal_Measurement(
                string_dmx=k, fcd=initial_val + (rand * drop)
            ))

        thermals_list.append(thermal_list)

    return thermals_list


def fake_messages(mn: int):
    thermals_list = make_measurements(mn)
    fake_messages_ = {
        938: thermals_list[0] + list(chain(*thermals_list[1:])) +
             [TestResult(status='PASS')],
        897: thermals_list[0] + [TestResult(status='PASS')]
    }
    return [fake_unit_data[mn]] + fake_messages_[mn]


class FakeData:
    def __init__(self, mn: int) -> None:
        self.messages = fake_messages(mn)
        self.params = fake_params[mn]


if __name__ == '__main__':
    for msg in fake_messages(897):
        print(msg)
