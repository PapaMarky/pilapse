#! /usr/bin/env python3

import argparse
import json
import threading
from datetime import datetime, timedelta

import camera_producer
from camera_producer import CameraProducer

from config import Config
from config import Configurable
import pilapse as pl
from queue import Queue
from threads import DirectoryProducer, MotionPipeline, ImageWriter
from scheduling import Schedule

import cv2
import imutils
import logging
import os
import sys
import time

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

class MotionConfig(Config):
    def __init__(self):
        super().__init__()

    def create_parser(self):
        parser = argparse.ArgumentParser(description='Capture images when motion is detected')


        frame.add_argument('--source-dir', type=str,
                           help='If source-dir is set, image files will be loaded from a directory instead of '
                                'the camera')


        general = parser.add_argument_group('General', 'Miscellaneous parameters')

        debugging = parser.add_argument_group('Debbuging / Troubleshooting')

        return parser


class MotionDetectionApp(Configurable):

    ARGS_ADDED = False
    @classmethod
    def add_arguments_to_parser(cls, parser:argparse.ArgumentParser, argument_group_name:str='Motion Settings')->argparse.ArgumentParser:
        logging.info(f'Adding motion detection args to parser (ADDED:{MotionDetectionApp.ARGS_ADDED})')
        motion = parser.add_argument_group(argument_group_name, 'Parameters related to motion detection')
        motion.add_argument('--mindiff', '-m', type=int, help='Minimum size of "moving object" to detect', default=75)
        motion.add_argument('--top', '-t', type=float, help='top of region of interest. (0.0 - 1.0) '
                                                            'Ignore any motion above this',
                            default=0.0)
        motion.add_argument('--bottom', '-b', type=float, help='bottom of region of interest. (0.0 - 1.0) '
                                                               'Ignore any motion below this',
                            default=1.0)
        motion.add_argument('--left', '-l', type=float, help='left of region of interest. (0.0 - 1.0) '
                                                             'Ignore any motion left of this',
                            default=0.0)
        motion.add_argument('--right', '-r', type=float,
                            help='right of region of interest. (0.0 - 1.0) '
                                 'Ignore any motion to the right of this',
                            default=1.0)
        motion.add_argument('--shrinkto', type=float,
                            help='Shrink images to this height for analysis. This can speed up analysis. '
                                 'If this value is a float, it will be interpreted as percentage', default=None)
        motion.add_argument('--threshold', type=int,
                            help='cut off threshold for detecting changes (0 - 255)',
                            default=25)
        motion.add_argument('--dilation', type=int, default=3,
                            help='Number of dilation iterations to perform')
        motion.add_argument('--save-diffs', action='store_true',
                               help='also save the diffed images for debugging')
        motion.add_argument('--show-motion', action='store_true',
                               help='Highlight motion in output images.')
        motion.add_argument('--testframe', action='store_true',
                               help='Write a test frame with layout information.')

        motion.add_argument('--all-frames', action='store_true',
                           help='Save all images even when no motion is detected')

        MotionDetectionApp.ARGS_ADDED = True
        # Add the args of Configurables that MotionDetectionApp uses
        CameraProducer.add_arguments_to_parser(parser)
        DirectoryProducer.add_arguments_to_parser(parser)
        ImageWriter.add_arguments_to_parser(parser)

        return parser

    def __init__(self):
        self._version = '1.0.0'
        self._camera_producer:CameraProducer = None
        self._directory_producer:DirectoryProducer = None
        self._motion_pipeline:MotionPipeline = None
        self._image_writer:ImageWriter = None

        parser = Configurable.create_parser('Motion Detection App for Raspberry Pi')
        self._parser = MotionDetectionApp.add_arguments_to_parser(parser)
        self._config = self.load_from_list(self._parser)
        MotionDetectionApp.validate_config(self._config)
        #if self._config is None:
        #    raise Exception('Bad config')

        if not pl.it_is_time_to_die():
            self.process_config(self._config)
            self.front_queue = Queue()
            self.back_queue = Queue()
            self._shutdown_event = threading.Event()

    def load_from_list(self, parser, arglist=None):
        logging.info('loading MOTION config from list:')

        config = super().load_from_list(parser, arglist=arglist)
        self.dump_to_log(config)

        return config

    def process_config(self, config):
        logging.info(f'CONFIG: {config}')
        super().process_config(config)

        self.bottom = int(self._config.bottom * self._config.height)
        self.top = int(self._config.top * self._config.height)
        self.left = int(self._config.left * self._config.width)
        self.right = int(self._config.right * self._config.width)

        if self._config.shrinkto is not None:
            logging.debug('shrinkto is set')
            if self._config.shrinkto <= 1.0:
                self.shrinkto = int(self._config.height * self._config.shrinkto)

    def run(self):
        if pl.it_is_time_to_die():
            return
        ###
        # Create a Motion Consumer and Image Producer. Start them up.

        producer = None
        if self._config.source_dir:
            # load images from directory
            producer = DirectoryProducer('png', self._shutdown_event, self._config, out_queue=self.front_queue)
            self._directory_producer = producer
        else:
            # create images using camera
            producer = CameraProducer(self._shutdown_event, self._config, out_queue=self.front_queue)
            self._camera_producer = producer
        self._motion_pipeline = MotionPipeline(self._shutdown_event, self._config, in_queue=self.front_queue, out_queue=self.back_queue)
        self._image_writer = ImageWriter(self._shutdown_event, self._config, in_queue=self.back_queue)

        self._image_writer.start()
        self._motion_pipeline.start()
        producer.start()

        while True:
            logging.debug(f'waiting: producer alive? {producer.is_alive()}, consumer alive? '
                          f'{self._motion_pipeline.is_alive()} writer alive? {self._image_writer.is_alive()}')
            if not producer.is_alive() or not self._motion_pipeline.is_alive() or not self._image_writer.is_alive():
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

                logging.info('Waiting for pipeline...')
                try:
                    pipeline.join(5.0)
                    if pipeline.is_alive():
                        logging.warning('- Timed out, pipeline is still alive.')
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
            time.sleep(1)
        pl.die()

def main():
    try:
        app = MotionDetectionApp()
        if not pl.create_pid_file():
            pl.die()
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