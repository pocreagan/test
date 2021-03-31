from multiprocessing import freeze_support

from src.base.load import dynamic_import
from src.model.resources import APP, logger


def hidden_imports() -> None:
    """
    explicit import statements needed in main.py for binary build module discovery
    importing in function scope to prevent unnecessary imports on controller spawn
    """
    from src.framework import view
    import src.framework.view.chart.concrete_widgets
    from src.lighting.LL2 import chart as c2
    from src.lighting.LL2 import controller as con2
    from src.lighting.LL2 import view as v2
    from src.lighting.LL3 import chart as c3
    from src.lighting.LL3 import controller as con3
    from src.lighting.LL3 import view as v3


def main() -> None:
    """
    configure and start the main process logger
    load and start the view and controller
    """
    APP.log_runtime_info()
    log = logger(__name__)
    log.info(f'Starting Application {APP.TITLE}...')

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
        logger.format().to_window(view).start()

        # add widgets, set to initial state, and run Tk mainloop (blocking in this thread)
        view.start()

    finally:
        # wait for the controller process to finish
        controller.q.put_sentinel()
        controller.join(timeout=1.)
        log.info('closed Controller')

    log.info(f'Closed Application {APP.TITLE}.')

    # stop listening to the main process logging enqueue queue
    logger.stop()


if __name__ == '__main__':
    freeze_support()  # needed here for binary build

    main()
