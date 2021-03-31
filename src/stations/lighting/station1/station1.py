from src.instruments.daqs.pixie_panel_daq import PanelIDTask
from src.instruments.daqs.pixie_panel_daq import BoardPowerTask, CurrentDrawTask
from src.base.log import logger

log = logger(__name__)


def do():
    panel_id = PanelIDTask()
    panel_id.instrument_setup()
    panel_id = panel_id.proxy_spawn()

    board_p = BoardPowerTask()
    board_p.instrument_setup()
    board_p = board_p.proxy_spawn()

    current_draw = CurrentDrawTask()
    current_draw.instrument_setup()
    current_draw = current_draw.proxy_spawn()

    duration = 5
    current_draw_promise = current_draw.test(duration)
    board_p_promise = board_p.test(duration)
    panel_id_promise = panel_id.test(duration)

    current_draw_promise.resolve()
    board_p_promise.resolve()
    panel_id_promise.resolve()


if __name__ == '__main__':
    with logger:
        do()
