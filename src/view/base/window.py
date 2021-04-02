import tkinter as tk
from typing import List

from src.base.concurrency.message import *
from src.base.log import logger
from src.model.resources import APP
from src.model.resources import COLORS
from src.model.resources import RESOURCE
from src.view.base.human_input import HID
from src.view.base.placement import *
from src.view.base.system import *

__all__ = [
    'Window',
]

log = logger(__name__)


class MockLogDeque:
    new: bool = False

    def get(self) -> List[str]:
        raise NotImplementedError


class Window(tk.Tk):
    screen: Screen
    font: TypeFace
    hid: HID
    log_deque: MockLogDeque
    pad_px: int

    def __init__(self) -> None:
        """
        lean init that only sets runtime constants and Tk init
        """
        log.debug('instantiating Window...')

        self.name = self.__class__.__name__
        self.constants = RESOURCE.cfg('view')['window']
        self.w_px, self.h_px = APP.STATION.resolution
        self.widgets_by_position = dict()
        self.categories = self.categories or dict()
        self.poll_scheduled = None

        tk.Tk.__init__(self)

        log.debug('instantiated Window')

    def set_attribute(self, f: str, k: str, *v) -> None:
        """
        set one Tk attribute and log k, v pair
        """
        getattr(self, f)(k, *v)
        log.debug(f'set {f}: "{k}"')

    def configure_for_fullscreen(self) -> None:
        """
        set to fullscreen
        """
        self.set_attribute('attributes', '-fullscreen', True)

    def configure_for_partial_screen(self) -> None:
        """
        remove title bar, size window, and bind _on_move for lazy winfo_root access
        """
        self.overrideredirect(True)
        self.minsize(width=self.w_px, height=self.h_px)
        self.maxsize(width=self.w_px, height=self.h_px)

    def size_window(self) -> None:
        """
        measure screen and either set to fullscreen or widowed using ini values
        """
        self.screen = Screen(self)
        log.debug(f'app resolution from ini: {self.w_px}x{self.h_px}px')

        self.pad_px = int(self.constants['PADDING'] * self.screen.resolution_h)

        if (self.screen.resolution_w == self.w_px) and (self.screen.resolution_h == self.h_px):
            self.configure_for_fullscreen()

        else:
            self.configure_for_partial_screen()

        self.resizable(0, 0)

    def set_attributes(self) -> None:
        """
        set window to always topmost if indicated in ini, when running as production app
        attach close method to alt-f4 and window close
        """
        # self.set_attribute('attributes', '-topmost', True)
        # TODO: uncomment vvv and remove ^^^
        # if self.constants['FORCE_TOPMOST']:
        #     if APP.IS_PRODUCTION:
        #         self.set_attribute('attributes', '-topmost', True)
        #
        #     else:
        #         log.warning('did not set window attribute -topmost because not APP.IS_PRODUCTION')

        self.set_attribute('protocol', 'WM_DELETE_WINDOW', self.close)

    def style(self) -> None:
        """
        set Window-level style attributes
        """
        self.title(APP.name)
        self.config(bg=COLORS.black)
        self.font = TypeFace(RESOURCE.font(self.constants['font']))

    def configure_window(self) -> None:
        """
        set top-level attributes etc
        """
        self.size_window()
        self.set_attributes()
        self.style()

    def add_widget(self, widget: WidgetPosition) -> None:
        """
        takes widget as (Cell subclass, Pos(x, y, w, h), name or None)
        if widget has not been added at pos, shows widget
        """
        instance = widget.widget(widget.name, self, *widget.pos)
        setattr(self, widget.name, instance)

        category = self.categories.get(widget.pos, None)
        if category:
            category.add(instance)
            log.debug(f'widget <{widget.name}> added to category <{category.name}>')

        log.debug(f'widget <{widget.name}> added to window')

        if widget.pos not in self.widgets_by_position:
            instance.show()

    def add_initial_widgets(self) -> None:
        """
        initial window widgets' setup
        """
        [self.add_widget(widget) for widget in self.widgets]
        self.categories = {cat.name: cat for cat in self.categories.values()}
        log.info(f'added all widgets')

    def __post_init__(self) -> None:
        """
        after setup and before first poll
        """

    def _setup_window(self) -> None:
        """
        load and configure view
        perform Tk config and appearance changes
        add hid bindings and initial widgets
        """
        log.info(f'STARTED.')

        self.hid = HID(self)
        self.configure_window()
        self.add_initial_widgets()

        self.__post_init__()

        log.info('View loaded')
        self.after(50, self.start_polling)

    def start(self) -> None:
        """
        perform actions between init and mainloop, then call mainloop
        """
        log.info(f'STARTING...')

        self.after(10, self._setup_window)

        self.update()

        self.mainloop()  # ! blocking in main thread

    def destroy_all_widgets(self) -> None:
        """
        final window widgets' teardown
        """
        [widget.destroy() for widget in list(self.children.values())]
        log.info(f'destroyed all widgets')

    def close(self) -> None:
        """
        perform actions before main process close
        """
        log.info('CLOSING...')

        self.hid.unbind()

        if self.poll_scheduled:
            self.after_cancel(self.poll_scheduled)

        self.destroy_all_widgets()
        self.quit()
        self.destroy()

        log.info('CLOSED')

    def start_polling(self) -> None:
        """
        get started msg from controller and start polling
        """
        with self.hid:
            self._q.get()

        log.info('start message received from controller')

        self.poll()

    def handle_keyboard_action(self, msg: KeyboardAction) -> None:
        """
        possible Window methods are defined in view.yml
        else passes the action to the controller and returns
        """
        method = getattr(self, msg.f, None)
        if method:
            with self.hid:
                if method(*msg.args) is not False:
                    return log.info(f'Window handled {msg}')

        self._q.put(msg)
        log.debug(f'{msg} had no effect')

    def poll(self) -> None:
        """
        perform running work
        ex.: check controller queue
        """
        raise NotImplementedError
