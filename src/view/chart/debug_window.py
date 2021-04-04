import tkinter as tk
from time import perf_counter
from time import sleep
from typing import List

from src.base.log import logger
from src.view.chart.base import Root

log = logger(__name__)


class LogTimeElapsed:
    def __init__(self, action: str) -> None:
        self._action = action

    def __enter__(self) -> None:
        self._ti = perf_counter()

    def __exit__(self, *e) -> None:
        tf = perf_counter()
        log.info(f'{self._action} in {(tf - self._ti)*1000:.1f}ms')


class ChartDebugWindow(tk.Tk):
    def set_attribute(self, f: str, k: str, *v) -> None:
        getattr(self, f)(k, *v)
        log.debug(f'set {f}: "{k}" -> {v}')

    def cancel_scheduled(self) -> None:
        if self._poll_scheduled is not None:
            self.after_cancel(self._poll_scheduled)

    def close(self, *_: tk.EventType) -> None:
        self.cancel_scheduled()
        self.quit()
        self.destroy()

    def __init__(self, plot: Root, messages: List) -> None:
        tk.Tk.__init__(self, __name__)
        self.set_attribute('protocol', 'WM_DELETE_WINDOW', self.close)
        self.resizable(0, 0)

        self._plot = plot
        self._messages = messages
        self._message_iter = None
        self._poll_scheduled = None
        self._stopped = False

        with LogTimeElapsed('background set'):
            self._plot.set_background()
        with LogTimeElapsed('tk widget made'):
            self._chart = self._plot.for_tk(self)
            self._chart.update()

        self.bind('a', self.start_animation)
        self.bind('o', self.one_shot)
        self.bind('c', self.init_chart)
        self.bind('q', self.close)

    def init_chart(self, *_: tk.EventType) -> None:
        [self.cancel_scheduled() for _ in range(10000)]
        with LogTimeElapsed('plot initialized'):
            self._plot.init()
            self._chart.update()
        self.update()

    def start_animation(self, *_: tk.EventType) -> None:
        self.init_chart()
        self._message_iter = iter(self._messages)
        self._poll_scheduled = self.after_idle(self.poll)

    def one_shot(self, *_: tk.EventType) -> None:
        self.init_chart()
        with LogTimeElapsed('plot populated'):
            self._plot.populate_from_iteration(self._messages[-1])
            self._chart.update()
        self.update()

    def poll(self) -> None:
        try:
            message = next(self._message_iter)

        except StopIteration:
            pass

        except Exception as e1:
            try:
                self.close()
            except Exception as e2:
                raise e1 from e2
            raise e1

        else:
            self._plot(message)
            self._chart.update()
            self._poll_scheduled = self.after_idle(self.poll)
