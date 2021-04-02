import datetime
from typing import *

from src.base.log import logger
from src.model.resources import APP
from src.view.base.cell import *

__all__ = [
    'TestTitle',
    'TitleBar',
    'Build',
    'Time',
    'Logo',
    'WIDGET',
    'WIDGET_TYPE',
]

log = logger(__name__)


class Logo(Static.Image):
    """
    wet logo generated from EVA svg
    """
    filepath = 'wet_logo.png'
    _move_window = True
    _force_enabled = True

    def move(self, dx: int, dy: int) -> Optional[str]:
        self.parent.geometry((f'+{dx + self.parent.winfo_x()}'
                              f'+{dy + self.parent.winfo_y()}'))
        return 'break'


class TestTitle(Static.String):
    """
    show human readable test station title
    """
    string = APP.STATION.human_readable


class TitleBar(Static.String):
    """
    show software title/version and station hostname
    """
    string = APP.TITLE


class Build(Static.String):
    """
    show interpreter version if script or build type if binary
    """
    string = APP.BUILD_TYPE.lower()


class Time(Static.String):
    """
    show current time formatted per ini
    takes the place of an is_alive Window.after
    """
    string = '-'
    _fmt: str

    def _update_time(self) -> None:
        self.label.text(datetime.datetime.now().strftime(self._fmt))
        self.schedule(self._update_interval_ms, self._update_time)

    def __post_init__(self):
        self._fmt = self.constants['DT_FORMAT']
        self._update_interval_ms = self.constants['UPDATE_INTERVAL_MS']
        super().__post_init__()

    def _on_show(self):
        self.schedule(self._update_interval_ms, self._update_time)


WIDGET = Union[
    TestTitle,
    TitleBar,
    Build,
    Time,
    Logo,
]

WIDGET_TYPE = Type[WIDGET]
