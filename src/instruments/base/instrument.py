from functools import wraps
from inspect import currentframe
from itertools import count
from time import sleep
from time import time
from typing import Callable
from typing import Optional
from typing import Type
from typing import TypeVar

# noinspection SpellCheckingInspection
from src.base import atexit_proxy as atexit
from src.base import register
from src.base.concurrency import proxy
from src.model.configuration import update_configs_on_object
from src.base.concurrency.proxy import CancelledError
from src.base.general import setdefault_attr_from_factory
from src.base.log import logger
from src.base.log.mixin import Logged

__all__ = [
    'Instrument',
    'StringInstrument',
    'InstrumentError',
    'instrument_debug',
    'InstrumentHandler',
    'instruments_joined',
    'instruments_spawned',
]


class InstrumentError(Exception):
    pass


# noinspection PyTypeChecker
_T = TypeVar('_T', bound='Instrument')
_test_instruments_key = '_test_instrument_key_'


def instrument_debug(cls: Type[_T]) -> Optional[Type[_T]]:
    if currentframe().f_back.f_globals['__name__'] == '__main__':
        return cls.instrument_debug()
    return cls


class Instrument(Logged, proxy.Mixin, register.Mixin):
    _should_be_open = False
    TX_WAIT_S: float

    _next_tx: float = 0.

    def __set_name__(self, owner: 'InstrumentHandler', name: str) -> None:
        setdefault_attr_from_factory(owner, _test_instruments_key, dict)[name] = self
        setattr(owner, name, self)

    def __get__(self, instance, owner):
        return self

    def set_next_tx_time(self) -> None:
        self._next_tx = time() + self.TX_WAIT_S

    @register.before('__init__')
    def _instrument_set_constants_(self) -> None:
        update_configs_on_object(self)
        self._should_be_open = False
        self._instrument_check_flags = []
        self.name = type(self).__qualname__

    def instrument_add_check_flag(self, flag) -> None:
        self._instrument_check_flags.append(flag)

    def instrument_check_flags(self) -> None:
        for flag in self._instrument_check_flags:
            if flag.is_set():
                raise CancelledError()

    def _instrument_delay(self, te: float) -> None:
        if te > 0.:
            tf = time() + te
            for _ in count():
                self.proxy_check_cancelled()
                self.instrument_check_flags()
                t = time()
                if t > tf:
                    break
                sleep(max(0., min(.001, tf - t)))

    def _instrument_setup(self) -> None:
        """
        perform actual instrument_setup here
        """
        raise NotImplementedError

    def _instrument_cleanup(self) -> None:
        """
        perform actual teardown here
        """
        raise NotImplementedError

    def _instrument_check(self) -> None:
        """
        perform actual te instrument_check here
        raise exception on instrument_check failure
        """
        raise NotImplementedError

    @proxy.exposed
    def instrument_check(self) -> bool:
        """
        positively determine whether the gear is responding here
        """
        # SUPPRESS-LINTER <intended to fail>
        # noinspection PyBroadException
        try:
            self._instrument_check()

        except CancelledError:
            raise

        except Exception as e:
            self.warning(f'failed in ._instrument_check with {type(e)}("{str(e)}")')
            return False

        else:
            return True

    @proxy.exposed
    def instrument_setup(self) -> None:
        if (not self._should_be_open) or (not self.instrument_check()):
            self.instrument_cleanup()
            try:
                self._instrument_setup()

            except Exception as e:
                raise InstrumentError(f'failed in ._instrument_setup()') from e

            else:
                self.set_next_tx_time()
                self._should_be_open = True
                self.info(f'setup successful')

            finally:
                atexit.register(self.instrument_cleanup)

    @proxy.exposed
    def instrument_cleanup(self) -> None:
        # SUPPRESS-LINTER <don't care if this fails>
        # noinspection PyBroadException
        try:
            self._instrument_cleanup()

        except Exception as e:
            if (not isinstance(e, AttributeError)) or self._should_be_open:
                _type = e if isinstance(e, type) else type(e)
                s = f'{_type.__name__} ignored from ._instrument_cleanup()'
                (self.exception if self._should_be_open else self.warn)(s)

        else:
            self.info(f'cleanup successful')

        finally:
            self._should_be_open = False
            atexit.unregister(self.instrument_cleanup)

    def _instrument_debug(self) -> None:
        raise NotImplementedError

    @classmethod
    def instrument_debug(cls: Type[_T], f: Callable[[_T], None] = None, with_comm: bool = True) -> None:
        with logger:
            o: 'Instrument' = cls()

            if with_comm:
                o.instrument_setup()

            try:
                if f is None:
                    # noinspection PyArgumentList
                    return cls._instrument_debug(o)
                f(o)

            except KeyboardInterrupt:
                print(f'{cls.__name__}.instrument_debug interrupted')

            finally:
                if with_comm:
                    o.instrument_cleanup()

    def proxy_spawn_guard(self) -> Optional[str]:
        if not self._should_be_open:
            return 'must perform instrument_setup before spawning proxy server'


class StringInstrument(Instrument):
    ENCODING: str
    TERM_CHAR: str

    def _instrument_setup(self) -> None:
        raise NotImplementedError

    def _instrument_cleanup(self) -> None:
        raise NotImplementedError

    def _instrument_check(self) -> None:
        raise NotImplementedError

    def _instrument_debug(self) -> None:
        raise NotImplementedError

    def _prep_command(self, data: str) -> bytes:
        return f'{data}{self.TERM_CHAR}'.encode(self.ENCODING)

    def _strip_command(self, data: bytes) -> str:
        return data.decode(self.ENCODING).strip()

    def _receive(self, number_of_bytes: int = None):
        raise NotImplementedError

    def _send(self, packet) -> None:
        raise NotImplementedError

    def read(self, n: int = None) -> str:
        self.proxy_check_cancelled()
        rx = self._receive(n)
        self.debug(f'receive -> "{rx}"')
        return rx

    def write(self, packet: str) -> None:
        self._instrument_delay(self._next_tx - time())
        self._send(packet)
        self.set_next_tx_time()
        self.debug(f'transmit -> "{packet}"')


_TC = TypeVar('_TC')


def with_method_done(method_name: str):
    def outer(f: _TC) -> _TC:
        @wraps(f)
        def inner(self, *args, **kwargs):
            getattr(self, method_name)()
            try:
                return f(self, *args, **kwargs)
            finally:
                self.instruments_return_to_last_state()

        return inner  # type: ignore

    return outer


instruments_joined = with_method_done('instruments_join')
instruments_spawned = with_method_done('instruments_spawn')


class InstrumentHandler(register.Mixin, Logged):
    @register.before('__init__')
    def _build_instrument_list(self) -> None:
        self.last_spawn_state = False
        self.instruments_spawned = False
        self.instruments = getattr(self, _test_instruments_key, {})

    def __instrument(self, method_name: str) -> None:
        [getattr(inst, method_name)() for inst in self.instruments.values()]

    def __proxy(self, method_name: str) -> None:
        [setattr(self, k, getattr(v, method_name)()) for k, v in self.instruments.items()]
        self.instruments_spawned, self.last_spawn_state = 'spawn' in method_name, self.instruments_spawned

    def instruments_return_to_last_state(self) -> None:
        if self.last_spawn_state:
            self.instruments_spawn()
        else:
            self.instruments_join()

    def instruments_setup(self) -> None:
        """
        setup work after the individual instruments set themselves up
        """
        raise NotImplementedError

    @register.before('instruments_setup')
    @instruments_joined
    def _instruments_setup(self) -> None:
        self.__instrument('instrument_setup')

    @instruments_joined
    def instruments_cleanup(self) -> None:
        self.__instrument('instrument_cleanup')

    def instruments_spawn(self) -> None:
        self.__proxy('proxy_spawn')

    def instruments_join(self) -> None:
        self.__proxy('proxy_join')
