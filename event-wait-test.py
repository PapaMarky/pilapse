import logging
import signal
from threading import Event

event = Event()


def exit_gracefully(signum, frame):
    logging.info(f'SHUTTING DOWN due to {signal.Signals(signum).name}')
    event.set()

signal.signal(signal.SIGINT, exit_gracefully)
signal.signal(signal.SIGTERM, exit_gracefully)

while True:
    print('waiting...')
    event.wait(30)
    if event.is_set():
        break
print('quiting')