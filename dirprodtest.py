import logging
import sys
import time

import pilapse as pl

from threading import Event
from pilapse.threads import DirectoryProducer, MotionPipeline
from queue import Queue

path = sys.argv[1]
logging.info(f'STARTING TEST: {path}')
q = Queue()
shutdown_event = Event()

producer = DirectoryProducer(path, 'png', q, shutdown_event)
consumer = MotionPipeline(q, shutdown_event)

producer.start()
consumer.start()

while True:
    if pl.it_is_time_to_die():
        print('Shutting down...')
        shutdown_event.set()
        logging.info('Waiting for producer...')
        producer.join(5.0)
        if producer.is_alive():
            logging.warning('- Timed out, producer is still alive.')

        logging.info('Waiting for consumer...')
        consumer.join(5.0)
        if consumer.is_alive():
            logging.warning('- Timed out, consumer is still alive.')

        break
    time.sleep(1)
