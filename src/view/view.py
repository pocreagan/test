import queue
from collections import defaultdict
from dataclasses import asdict
from typing import DefaultDict
from typing import Optional
from typing import Set
from typing import Tuple
from typing import Type
from typing import Union

from src.base.concurrency.concurrency import *
from src.base.log import logger
from src.base.log.objects import Handler
from src.model.db import connect
from src.model.resources import APP
from src.model.vc_messages import ViewInitDataMessage
from src.view.base.window import Window

__all__ = [
    'View',
]

log = logger(__name__)


class View(Window):  # type: ignore
    log_deque: Optional[Handler.Deque] = None

    def __init__(self, q: ProcessConnection) -> None:
        self._poll_interval = APP.G['POLLING_INTERVAL_MS']

        self._q = q
        self._registered_messages = CallbackRegistry()
        self.subscribed_methods: DefaultDict[Type, Set[Union[str, Tuple[str, str]]]] = defaultdict(set)
        self.session_manager = connect()

        Window.__init__(self)

    def start_polling(self) -> None:
        Window.start_polling(self)
        self.publish(ViewInitDataMessage())

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

    def publish(self, message) -> None:
        """
        put message to controller queue
        """
        self._q.put(message)

    def handle_message(self, message) -> None:
        """
        get method name from message type
        execute it with args taken from message fields
        """
        methods = self.subscribed_methods.get(type(message), None)
        if methods is None:
            return log.warning(f'{message} from controller unhandled')
        for method in methods:
            if isinstance(method, tuple):
                widget, method = method
                method = getattr(getattr(self, widget), method)
            else:
                method = getattr(self, method, None)
            if hasattr(message, '__dataclass_fields__'):
                method(**asdict(message))
            else:
                method(message)

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
