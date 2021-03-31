import queue
import threading
import time

from src.base.concurrency.concurrency import make_duplex_connection
from src.base.concurrency.concurrency import ThreadConnection
from src.base.log import logger
from src.controller.lighting.pixie_hack import Pixie2pt0Station
from src.pixie_hack.view import GUI


if __name__ == '__main__':
    with logger:
        q1, q2 = queue.Queue(), queue.Queue()
        view_q, cont_q = make_duplex_connection(ThreadConnection, q1, q2, q2, q1)
        controller = Pixie2pt0Station(cont_q)
        t = threading.Thread(name='controller', target=controller.mainloop)
        t.start()
        GUI(view_q).mainloop()

        while t.is_alive():
            time.sleep(.1)
