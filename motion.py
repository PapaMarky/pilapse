#! /usr/bin/env python3

import argparse
import json
import threading
from datetime import datetime, timedelta

from config import Config
import pilapse as pl
from queue import Queue
from threads import DirectoryProducer, MotionPipeline, ImageWriter

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

        motion = parser.add_argument_group('Motion Detection', 'Parameters that control motion detection')
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
        motion.add_argument('--all-frames', action='store_true',
                               help='Save all frames even when no motion is detected')

        frame = parser.add_argument_group('Frame Setup', 'Parameters that control the generated frames')
        frame.add_argument('--width', '-W', type=int, help='width of each frame', default=640)
        frame.add_argument('--height', '-H', type=int, help='height of each frame', default=480)
        frame.add_argument('--zoom', type=float, help='Zoom factor. Must be greater than 1.0', default=1.0)
        frame.add_argument('--outdir', type=str,
                           help='directory where frame files will be written.',
                           default='./%Y%m%d')
        frame.add_argument('--prefix', type=str, default='motion',
                           help='Prefix frame filenames with this string')
        frame.add_argument('--show-name', action='store_true',
                           help='Write a timestamp on each frame')
        frame.add_argument('--label-rgb', type=str,
                           help='Set the color of the timestamp on each frame. '
                                'FORMAT: comma separated integers between 0 and 255, no spaces EX: "R,G,B" ')
        frame.add_argument('--source-dir', type=str,
                           help='If source-dir is set, image files will be loaded from a directory instead of '
                                'the camera')
        frame.add_argument('--framerate', type=float, default=None,
                               help='When "all-frames" is set, "framerate" limits how often a new frame is taken. '
                                    'Int value. Units is seconds. EX. Setting framerate to "3" will take a frame every'
                                    '3 seconds. Defaults to 0 which means "as fast as you can" ')

        timing = parser.add_argument_group('Timing', 'Control when capture starts / stops')
        timing.add_argument('--stop-at', type=str,
                             help='Stop loop when time reaches "stop-at". Format: HH:MM:SS with HH in 24 hour format')
        timing.add_argument('--run-from', type=str,
                             help='Only run after this time of day. (Format: HH:MM:SS with HH in 24 hour format)')
        timing.add_argument('--run-until', type=str,
                             help='Only run until this time of day. (Format: HH:MM:SS with HH in 24 hour format)')
        timing.add_argument('--nframes', type=int,
                             help='Stop after writing this many frames. (useful for testing setup)')

        general = parser.add_argument_group('General', 'Miscellaneous parameters')
        general.add_argument('--loglevel', type=str,
                             help='Set the log level.')
        general.add_argument('--save-config', action='store_true', help='Save config to jsonfile and exit.')

        debugging = parser.add_argument_group('Debbuging / Troubleshooting')
        debugging.add_argument('--save-diffs', action='store_true',
                               help='also save the diffed images for debugging')
        debugging.add_argument('--debug', action="store_true",
                               help='Turn on debugging of motion analysis. Shows features too small or outside' \
                                    'region of interest')
        debugging.add_argument('--show-motion', action='store_true',
                               help='Highlight motion even when debug is false.')
        debugging.add_argument('--testframe', action='store_true',
                               help='Write a test frame with layout information.')

        return parser

    def load_from_list(self, arglist=None):
        logging.info('loading MOTION config from list:')
        config = super().load_from_list(arglist=arglist)
        self.dump_to_log(config)

        if config.save_config:
            config_file = 'motion-config.json'
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

        if config.stop_at is not None and (config.run_from is not None or config.run_until is not None):
            print(f'If stop-at is set, run-until and run-from cannot be set')
            return None

        if config.run_from is not None or config.run_until is not None:
            # if either are set, both must be set.
            if config.run_from is None or config.run_until is None:
                print('if either run-from or run-until are set, both must be set')
                return None
        return config

class MotionDetectionApp():
    def __init__(self):
        self._config_loader = MotionConfig()
        self._config = self._config_loader.load_from_list()

        if self._config is None:
            raise Exception('Bad config')

        # placeholders for all the valid parameters
        self.mindiff = self._config.mindiff
        self.top = self._config.top
        self.bottom = self._config.bottom
        self.left = self._config.left
        self.right = self._config.right
        self.shrinkto = self._config.shrinkto
        self.threshold = self._config.threshold
        self.dilation = self._config.dilation
        self.all_frames = self._config.all_frames
        self.width = self._config.width
        self.height = self._config.height
        self.outdir = self._config.outdir
        self.prefix = self._config.prefix
        self.show_name = self._config.show_name
        self.label_rgb = self._config.label_rgb
        self.source_dir = self._config.source_dir
        self.stop_at = self._config.stop_at
        self.run_from = self._config.run_from
        self.run_until = self._config.run_until
        self.nframes = self._config.nframes
        self.loglevel = self._config.loglevel
        self.save_config = self._config.save_config
        self.save_diffs = self._config.save_diffs
        self.debug = self._config.debug
        self.show_motion = self._config.show_motion
        self.testframe = self._config.testframe

        if not pl.it_is_time_to_die():
            self.process_config()
            self.front_queue = Queue()
            self.back_queue = Queue()
            self._shutdown_event = threading.Event()


    def process_config(self):

        for k, v in self._config.__dict__.items():
            if k not in self.__dict__:
                logging.warning(f'Config attribute missing: {k}, config: {v}')
            self.__dict__[k] = v

        self.bottom = int(self.bottom * self.height)
        self.top = int(self.top * self.height)
        self.left = int(self.left * self.width)
        self.right = int(self.right * self.width)

        if self.shrinkto is not None:
            logging.debug('shrinkto is set')
            if self.shrinkto <= 1.0:
                self.shrinkto = self.height * self.shrinkto
            self.shrinkto = int(self.shrinkto)

        if self._config.zoom < 1.0:
            msg = f'Zoom must be 1.0 or greater. (set to: {self._config.zoom})'
            sys.stderr.write(msg + '\n')
            logging.error(msg)
            pl.die()

        if self.stop_at is not None:
            logging.debug(f'Setting stop-at: {self.stop_at}')
            (hour, minute, second) = self.stop_at.split(':')
            self.stop_at = datetime.now().replace(hour=int(hour), minute=int(minute), second=int(second), microsecond=0)

        if self.run_from is not None:
            logging.debug(f'Setting run-until: {self.run_from}')
            self.__dict__['run_from_t'] = datetime.strptime(self.run_from, '%H:%M:%S').time()

        if self.run_until is not None:
            logging.debug(f'Setting run-until: {self.run_until}')
            self.__dict__['run_until_t'] = datetime.strptime(self.run_until, '%H:%M:%S').time()

        if self.label_rgb is not None:
            (R,G,B) = self.label_rgb.split(',')
            self.label_rgb = BGR(int(R), int(G), int(B))

    def run(self):
        if pl.it_is_time_to_die():
            return
        ###
        # Create a Motion Consumer and Image Producer. Start them up.

        producer = None
        if self.source_dir:
            # load images from directory
            producer = DirectoryProducer(self.source_dir, 'png', self._shutdown_event, self._config, out_queue=self.front_queue)
        else:
            # create images using camera
            from camera_producer import CameraProducer
            producer = CameraProducer(self.width, self.height, self._config.zoom, self._config.prefix,
                                      self._shutdown_event, self._config, out_queue=self.front_queue)
        pipeline = MotionPipeline(self._shutdown_event, self._config, in_queue=self.front_queue, out_queue=self.back_queue)
        writer = ImageWriter(self._shutdown_event, self._config, in_queue=self.back_queue)

        writer.start()
        pipeline.start()
        producer.start()

        while True:
            logging.debug(f'waiting: producer alive? {producer.is_alive()}, consumer alive? '
                          f'{pipeline.is_alive()} writer alive? {writer.is_alive()}')
            if not producer.is_alive() or not pipeline.is_alive() or not writer.is_alive():
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
            now = datetime.now()
            if self.stop_at and now > self.stop_at:
                logging.info(f'Shutting down due to "stop_at": {self.stop_at.strftime("%Y/%m/%d %H:%M:%S")}')
                pl.die()
            time.sleep(1)
        pl.die()

def main():
    try:
        if not pl.create_pid_file():
            pl.die()
        app = MotionDetectionApp()
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