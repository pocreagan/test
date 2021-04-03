import tkinter as tk
from operator import attrgetter
from typing import Type

from src.base.log import logger
from src.model.db import connect
from src.model.db.schema import LightingStation3Param
from src.stations.lighting.station3.chart import Plot
from src.view.chart.base import Root


class Window(tk.Tk):
    w = 1429
    h = 799

    def __init__(self, plot: Type[Root], params, **cfg) -> None:
        tk.Tk.__init__(self, __name__)
        self.plot = plot(params, **cfg)
        self.plot.set_background()
        self.chart = self.plot.for_tk(self)
        self.update()


if __name__ == '__main__':
    with logger:
        with connect(echo_sql=True)(expire=False) as session:
            params = LightingStation3Param.get(session, '918 brighter')
            rows = list(sorted(params.rows, key=attrgetter('row_num')))
        window = Window(Plot, rows, mn=918).mainloop()
