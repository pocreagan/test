import queue
import tkinter as tk
from tkinter import ttk

from singledispatchmethod import singledispatchmethod

from src.base.concurrency.concurrency import ConnectionClosed
from src.base.concurrency.concurrency import SentinelReceived
from src.base.concurrency.concurrency import ThreadConnection
from src.pixie_hack.messages import *


class ProgrammingIndicator:
    def __init__(self, parent: 'GUI', width: int) -> None:
        self.parent = parent
        self.value = tk.DoubleVar()
        self.progressbar = ttk.Progressbar(self.parent, variable=self.value, orient="horizontal",
                                           mode='determinate', maximum=1., length=width)
        self.last_value = 0.
        self.grid = self.progressbar.grid

    def setup(self, value: float) -> None:
        assert value != 0.
        self.progressbar['maximum'] = value
        self.set(0.)

    def increment(self) -> None:
        self.last_value += 1
        self.value.set(self.last_value)

    def set(self, val: float) -> None:
        self.last_value = min(val, self.progressbar['maximum'])
        self.value.set(self.last_value)
        self.progressbar.update()


class LabeledValue:
    def __init__(self, parent, label_text: str, font_size: int) -> None:
        self.frame = tk.Frame(parent)
        self.label = tk.Label(self.frame, text=label_text, font=("Arial", font_size))
        self.value = tk.StringVar()
        self.value_label = tk.Label(self.frame, font=("Arial", font_size), textvariable=self.value)
        self.label.grid(row=0, column=0)
        self.value_label.grid(row=0, column=1)
        self.grid = self.frame.grid
        self.set = self.value.set


class StringRow:
    def __init__(self, parent, font_size: int) -> None:
        self.frame = tk.Frame(parent)
        [self.frame.columnconfigure(pad=30, index=i) for i in range(5)]
        self.name_param = tk.StringVar()
        self.name_label = tk.Label(self.frame, textvariable=self.name_param,
                                   font=("Arial", font_size, 'bold'))
        self.name_label.grid(row=0, column=0)
        self.color_param = tk.StringVar()
        self.color_label = tk.Label(self.frame, textvariable=self.color_param, font=("Arial", font_size))
        self.color_label.grid(row=0, column=1, columnspan=2)
        self.brightness_param = tk.StringVar()
        self.brightness_label = tk.Label(self.frame, textvariable=self.brightness_param,
                                         font=("Arial", font_size))
        self.brightness_label.grid(row=0, column=3)
        self.power_param = tk.StringVar()
        self.power_label = tk.Label(self.frame, textvariable=self.power_param, font=("Arial", font_size))
        self.power_label.grid(row=0, column=4)

        self.row_result = tk.StringVar()
        self.row_result_label = tk.Label(self.frame, textvariable=self.row_result,
                                         font=("Arial", font_size, 'bold'))
        self.row_result_label.grid(row=1, column=0)
        self.color_result = tk.StringVar()
        self.color_result_label = tk.Label(self.frame, textvariable=self.color_result,
                                           font=("Arial", font_size, 'bold'))
        self.color_result_label.grid(row=1, column=1)
        self.color_dist_result = tk.StringVar()
        self.color_dist_result_label = tk.Label(self.frame, textvariable=self.color_dist_result,
                                                font=("Arial", font_size, 'bold'))
        self.color_dist_result_label.grid(row=1, column=2)
        self.brightness_result = tk.StringVar()
        self.brightness_result_label = tk.Label(self.frame, textvariable=self.brightness_result,
                                                font=("Arial", font_size, 'bold'))
        self.brightness_result_label.grid(row=1, column=3)
        self.power_result = tk.StringVar()
        self.power_result_label = tk.Label(self.frame, textvariable=self.power_result,
                                           font=("Arial", font_size, 'bold'))
        self.power_result_label.grid(row=1, column=4)

        self.grid = self.frame.grid

    def clear(self) -> None:
        for cell in (self.row_result, self.color_result, self.color_dist_result, self.brightness_result,
                     self.power_result):
            cell.set('')

    def set(self, dc: dataclass) -> None:
        dc.update_view(self)


class UnitData:
    def __init__(self, parent: 'GUI'):
        self.parent = parent
        self.frame = tk.Frame(self.parent)
        [self.frame.columnconfigure(pad=100, index=i) for i in range(2)]
        self.dut_id = LabeledValue(self.frame, 'DUT:  ', 14)
        self.dut_id.grid(row=0, column=0)
        self.uid = LabeledValue(self.frame, 'UID:  ', 14)
        self.uid.grid(row=0, column=1)
        self.result = LabeledValue(self.frame, 'Test Result:  ', 16)
        self.result.grid(row=0, column=2)
        self.grid = self.frame.grid


class GUI(tk.Tk):
    def __init__(self, q: ThreadConnection) -> None:
        self.q = q
        super().__init__('PixieHackTest')
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.resizable(False, False)

        [self.rowconfigure(pad=10, index=i) for i in range(8)]

        self.main_status_var = tk.StringVar()
        self.main_status = tk.Label(self, font=("Arial", 25), textvariable=self.main_status_var)
        self.main_status.grid(row=0, column=0, columnspan=5)
        self.main_status_var.set('ready')

        self.progress_bar = ProgrammingIndicator(self, 650)
        self.progress_bar.grid(row=1, column=0, columnspan=5)
        self.progress_bar.setup(25)

        self.unit_data = UnitData(self)
        self.unit_data.grid(row=2, column=0, columnspan=5)

        self.rows = [StringRow(self, 12) for _ in range(5)]
        for i, row in enumerate(self.rows):
            row.grid(row=3 + i, column=0, columnspan=5)

        self.after(100, self.poll)

    @singledispatchmethod
    def handle(self, *args) -> None:
        raise ValueError(f'no handler for args {args}')

    @handle.register
    def _(self, msg: Result) -> None:
        self.rows[msg.row].set(msg)
        self.progress_bar.increment()

    @handle.register
    def _(self, msg: Param) -> None:
        self.rows[msg.row].set(msg)

    @handle.register
    def _(self, msg: FirmwareSetup) -> None:
        self.main_status_var.set('programming')
        self.progress_bar.setup(msg.n)

    @handle.register
    def _(self, msg: StringsStart) -> None:
        _ = msg
        self.main_status_var.set('string checks')
        self.progress_bar.setup(len(self.rows))

    @handle.register
    def _(self, msg: FirmwareIncrement) -> None:
        _ = msg
        self.progress_bar.increment()

    @handle.register
    def _(self, msg: DUT) -> None:
        msg.update_view(self.unit_data)
        self.unit_data.result.value.set('')
        self.main_status_var.set('testing')
        [row.clear() for row in self.rows]
        self.progress_bar.set(0)

    @handle.register
    def _(self, msg: TestResult) -> None:
        self.unit_data.result.value.set('PASS' if msg.test_pf else 'FAIL')
        self.unit_data.result.value_label['fg'] = 'green' if msg.test_pf else 'red'
        self.main_status_var.set('ready')

    def close(self) -> None:
        self.q.put_sentinel()
        self.destroy()
        self.quit()

    def poll(self) -> None:
        try:
            list(map(self.handle, self.q.all))

        except queue.Empty:
            pass

        except (SentinelReceived, ConnectionClosed):
            return self.close()

        self.after(10, self.poll)
