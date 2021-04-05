from src.base.concurrency import *
from src.base.message import ControllerAction
from src.base.message import ViewAction
from src.model import *

__all__ = [
    'Controller',
]

log = logger(__name__)


class RS485(ChildTerminus):
    def __init__(self, parent):
        self.parent: 'Controller' = parent
        self.parent.children.append(self)
        self.__post_init__()

    def __post_init__(self) -> None:
        from src.stations.lighting.bright.FSM import FTDIFSM

        self._thread = FTDIFSM(self.parent._q, name='FTDI', log_name=__name__, )
        self._thread.start()
        self._thread.q.get()
        log.info('FTDI thread started')

    def do(self, _method: str, *args, **kwargs) -> None:
        self._thread.q.put((_method, args, kwargs))

    def close(self) -> None:
        self._thread.q.put_sentinel()
        self._thread.e.set()
        self._thread.join(timeout=.1)

    def dmx_change(self, sns, dmx: int) -> None:
        self.do('dmx_change', sns, dmx)

    def files(self, fp: str) -> None:
        self.do('files', fp)

    def configuration(self, fp: str, sns) -> None:
        self.do('config', fp, sns)

    def firmware(self, fp: str, sns) -> None:
        self.do('firmware', fp, sns)

    def poll(self) -> None:
        if not self._thread.is_alive():
            del self._thread
            self.__post_init__()

class Controller(parent_terminus(ControllerAction, ViewAction), Process):  # type: ignore
    _poll_delay_s = .01
    def __post_init__(self):
        logger.to_main_process(self._log_q).start()

        try:
            self._poll_delay_s = APP.G.POLLING_INTERVAL_MS / 1000
            self.perform_view_action = getattr(self, '_perform_other_action')
            self.children = list()
            self.rs485 = RS485(self)

        except Exception:
            log.warning('', exc_info=True)

        else:
            log.info('made cell counterparts')

        Process.__post_init__(self)

    def on_shutdown(self):
        [o.close() for o in self.children]

    def __init__(self, log_q):
        Process.__init__(self, log_q, name='Controller', log_name=__name__)
