#! /usr/bin/env python3

import argparse
import threading
from datetime import datetime, timedelta
from queue import Queue

from camera import Camera

from config import Config, Configurable
import pilapse as pl

import cv2
import logging
import os
import sys
import time
import pause

from scheduling import Schedule
from threads import ImageWriter
from camera_producer import CameraProducer


def BGR(r, g, b):
    return (b, g, r)

BLUE = BGR(0, 0, 255)
GREEN = BGR(0, 255, 0)
RED = BGR(255, 0, 0)
CYAN = BGR(0, 255, 255)
MAGENTA = BGR(255, 0, 255)
YELLOW = BGR(255, 255, 0)
ORANGE = BGR(255,165,0)
WHITE = BGR(255, 255, 255)

class TimelapseConfig(Config):
    def __init__(self):
        super().__init__()

    def create_parser(self):
        parser = argparse.ArgumentParser(description='Capture a series of image frames for creating a timelapse')


        general = parser.add_argument_group('General', 'Miscellaneous parameters')

        # TODO: Should camera producer have an "add_arguents" function since it owns the Schedule object?

        return parser

    def load_from_list(self, arglist=None):
        logging.info(f'loading {pl.get_program_name()} config from list')
        config = super().load_from_list(arglist=arglist)
        self.dump_to_log(config)

        if config.save_config:
            config_file = 'timelapse-config.json'
            logging.info(f'Saving config to {config_file}')
            config.save_config = False
            with open(config_file, 'w') as json_file:
                logging.info(f'Dict Type: {type(config.__dict__)}')
                logging.info(f'Dict: {config.__dict__}')
                json_file.write(json.dumps(config.__dict__, indent=2))
            pl.die()

        if config.loglevel is not None:
            oldlevel = logging.getLevelName(logging.getLogger().getEffectiveLevel())
            level = config.loglevel.upper()
            logging.info(f'Setting log level from {oldlevel} to {level}')
            logging.getLogger().setLevel(level)

        return config
class TimelapseApp(Configurable):

    ARGS_ADDED = False
    @classmethod
    def add_arguments_to_parser(cls, parser:argparse.ArgumentParser, argument_group_name:str='Motion Settings')->argparse.ArgumentParser:
        logging.debug(f'Adding motion detection args to parser (ADDED:{TimelapseApp.ARGS_ADDED})')
        Schedule.add_arguments_to_parser(parser)
        CameraProducer.add_arguments_to_parser(parser)
        ImageWriter.add_arguments_to_parser(parser)

        return parser

    def __init__(self):
        self._version = '1.0.0'
        self._camera_producer:CameraProducer = None
        self._image_writer:ImageWriter = None

        parser = Configurable.create_parser('Timelapse App for Raspberry Pi')
        self._parser = TimelapseApp.add_arguments_to_parser(parser)
        self._config = self.load_from_list(self._parser)
        TimelapseApp.validate_config(self._config)


        if not pl.it_is_time_to_die():
            self.process_config()
            self.out_queue = Queue()
            self._shutdown_event = threading.Event()

    def process_config(self):
        pass

    def run(self):
        if pl.it_is_time_to_die():
            return
        ###
        # Create a Motion Consumer and Image Producer. Start them up.

        producer = None
        # create images using camera
        producer = CameraProducer(self._shutdown_event, self._config, out_queue=self.out_queue)
        writer = ImageWriter(self._shutdown_event, self._config, in_queue=self.out_queue)

        writer.start()
        producer.start()

        while True:
            logging.debug(f'waiting: producer alive? {producer.is_alive()},  writer alive? {writer.is_alive()}')
            if not producer.is_alive() or not writer.is_alive():
                self._shutdown_event.set()
                pl.set_time_to_die()

            if pl.it_is_time_to_die():
                logging.info('Shutting down')
                self._shutdown_event.set()
                break

                logging.info('Waiting for producer...')
                try:
                    producer.join(5.0)
                    if producer.is_alive():
                        logging.warning('- Timed out, producer is still alive.')
                except Exception as e:
                    logging.exception(e)

                logging.info('Waiting for writer...')
                try:
                    writer.join(5.0)
                    if writer.is_alive():
                        logging.warning('- Timed out, writer is still alive.')
                except Exception as e:
                    logging.exception(e)

                break
            self._shutdown_event.wait(1)
            if self._shutdown_event.is_set():
                pl.set_time_to_die()
                break
        pl.die()

def main():
    try:
        if not pl.create_pid_file():
            pl.die()
        app = TimelapseApp()
        if not pl.it_is_time_to_die():
            app.run()
    except Exception as e:
        logging.exception('Exception in Main')
        logging.exception(e)
        pl.die(1)

if __name__ == '__main__':
    try:
        main()
        if pl.it_is_time_to_die():
            logging.info('Exiting: Graceful shutdown')
    except Exception as e:
        logging.exception(f'Unhandled Exception: {e}')
        pl.die(1)