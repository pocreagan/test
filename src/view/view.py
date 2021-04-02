import queue
from typing import Optional

from src.base.concurrency.concurrency import *
from src.base.concurrency.message import *
from src.base.log import logger
from src.base.log.objects import Handler
from src.model.resources import APP
from src.view.base.window import Window

__all__ = [
    'View',
]

log = logger(__name__)


class View(parent_terminus(ViewAction, ControllerAction), Window):  # type: ignore
    log_deque: Optional[Handler.Deque] = None

    def __init__(self, q: ProcessConnection) -> None:
        self._poll_interval = APP.G.get('POLLING_INTERVAL_MS')

        self._q = q
        self._registered_messages = CallbackRegistry()
        self.perform_controller_action = getattr(self, '_perform_other_action')
        Window.__init__(self)

    def close(self) -> None:
        self._q.put_sentinel()
        super().close()

    def dispatch(self, msg) -> None:
        """
        handle message received from the controller
        """
        self.handle_message(msg)
        self._q.task_done()

    def _prioritize(self, messages):
        """
        can be extended for prioritized message handling
        """
        _ = self
        return messages

    def _on_pipe_error(self):
        """
        when the duplex pipe connection closes on purpose or accident
        """
        log.error('PIPE CLOSED')
        self.close()

    def on_sentinel_received(self) -> None:
        """
        override hook
        """
        self._on_pipe_error()

    def on_connection_closed(self) -> None:
        """
        override hook
        """
        self._on_pipe_error()

    def poll(self) -> None:
        """
        checks for a new messages from the controller and passes them to dispatch
        if the controller exits on purpose or accident, closes the window
        """
        try:
            list(map(self.dispatch, self._prioritize(self._q.all)))

        except queue.Empty:
            self.poll_scheduled = self.after(self._poll_interval, self.poll)

        except SentinelReceived:
            self.on_sentinel_received()

        except ConnectionClosed:
            self.on_connection_closed()

        else:
            self.poll_scheduled = self.after(self._poll_interval, self.poll)
