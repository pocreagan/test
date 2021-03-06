from multiprocessing import freeze_support

from src.model.load import dynamic_import
from src.model.resources import APP
from src.model.resources import logger


# noinspection PyUnresolvedReferences
def hidden_imports() -> None:
    """
    explicit import statements needed in main.py for binary build module discovery
    importing in function scope to prevent unnecessary imports at runtime
    """
    from src.stations.lighting.station3 import chart, view, controller, model, test


def main() -> None:
    """
    configure and start the main process logger
    load and start the view and controller
    """
    log = logger(__name__)
    log.info(f'starting application {APP.TITLE}...')
    log.debug(APP.runtime_info())

    import_path = APP.STATION.import_path

    # instantiate controller outside try, finally statement so it can always be joined
    station_controller = getattr(dynamic_import('controller', *import_path), 'Controller')
    controller = station_controller(logger.q)

    try:
        # spawn controller process
        controller.start()

        # import window with its heavy image libraries while controller is spawning
        station_view = getattr(dynamic_import('view', *import_path), 'View')
        view = station_view(controller.q)

        # start main process record handlers
        logger.format().to_console().to_window(view).start()

        # add widgets, set to initial state, and run Tk mainloop (blocking in this thread)
        view.start()

    finally:
        # wait for the controller process to finish
        log.debug('stopping controller...')
        controller.q.put_sentinel()
        controller.join(timeout=5.)
        log.info('stopped controller')

    log.info(f'closed application {APP.TITLE}.')

    # stop listening to the main process logging enqueue queue
    logger.stop()


if __name__ == '__main__':
    freeze_support()  # needed here for binary build

    main()
