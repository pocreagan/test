import logging
from inspect import currentframe
from typing import Callable
from typing import TypeVar
from typing import Union

import click

from src.base.actor.proxy import exposed
from src.base.log import logger

__all__ = [
    'command_line',
    'cli',
]

log = logger(__name__)

_T = TypeVar('_T')


def cli(cls: _T) -> Union[_T, click.Group]:
    """
    code usage:
        @cli
        class Class:
            @exposed
            def method(...): ...

        - or -

        cli(Class)

    command line usage:
    py.exe -m module.path.from.src < *options > exposed_method_name < *arguments >

    example --help text for a trivial class:
        Usage: testing_clean.py [OPTIONS] COMMAND [ARGS]...

        Options:
        --log_level [NOTSET|DEBUG|INFO|WARNING|ERROR|CRITICAL]
        --help                          Show this message and exit.

        __Commands:
        do_something       (self) here is some documentation for the cli
        do_something_else  (self, a: int)

    does nothing if calling module was imported.
    pulls argument annotations from all method_names marked @exposed on an type by walking its MRO
    and exposes them as individual commands in a click CLI.
    options declared above "def group" are passed to any command through a context object.
    logging is not started until a command has been correctly supplied through the shell.
    """
    choices = ['NOTSET', 'DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
    bound_arguments = {'self', 'cls'}

    @click.group(name=f'{cls}')
    @click.option('--log_level', type=click.Choice(choices, case_sensitive=False), default='DEBUG')
    @click.pass_context
    def group(ctx: click.Context, log_level: str):
        ctx.obj = dict(obj=cls, log_level=getattr(logging, log_level))

    def make_command(method_: exposed) -> Callable[..., None]:
        def inner(ctx: click.Context, *args, **kwargs) -> None:
            logger.level = ctx.obj['log_level']
            with logger:
                instance = ctx.obj['obj']()
                _setup = getattr(instance, 'setup', None)
                if _setup:
                    _setup()

                try:
                    log.info(f'running {method_.name}')
                    log.info(getattr(instance, method_.name)(*args, **kwargs))

                finally:
                    _cleanup = getattr(instance, 'instrument_cleanup', None)
                    if _cleanup:
                        _cleanup()

        return inner

    def _guard_no_exposed_methods() -> None:
        if not _exposed_methods:
            raise TypeError(f'no method_names on {cls.__qualname__} have been exposed.')

    _exposed_methods = False
    for cla in cls.__mro__:
        for name, method in getattr(cla, exposed.registry_key, {}).items():  # type:str, exposed
            _exposed_methods = True

            f = click.pass_context(make_command(method))

            # SUPPRESS-LINTER <proven good>
            # noinspection PyTypeChecker
            for symbol, param in reversed(method.args_spec.parameters.items()):
                if symbol not in bound_arguments:
                    f = click.argument(symbol, type=param.annotation)(f)

            _doc = method.doc
            f.__doc__ = str(method.args_spec) + ':  ' + (_doc or '')
            group.command(name=name)(f)

    _guard_no_exposed_methods()
    group.__doc__ = cls.__doc__
    return group()


def command_line(cls: _T) -> _T:
    if currentframe().f_back.f_globals['__name__'] == '__main__':
        return cli(cls)
    return cls
