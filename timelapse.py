#! /usr/bin/env python3

import argparse
import threading
from datetime import datetime, timedelta
from queue import Queue

from camera import Camera

from config import Config
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

        motion = parser.add_argument_group('Motion Detection', 'Parameters that control motion detection')
        motion.add_argument('--debug', action="store_true",
                            help='Turn on debugging of motion analysis. Shows features too small or outside' \
                                 'region of interest')

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

        timelapse = parser.add_argument_group('Timelapse', 'Parameters that control timelapse')
        timelapse.add_argument('--framerate', type=float, default=None,
                               help='When "all-frames" is set, "framerate" limits how often a new frame is taken. '
                                    'Int value. Units is seconds. EX. Setting framerate to "3" will take a frame every'
                                    '3 seconds. Defaults to 0 which means "as fast as you can" ')
        # Internal variable that gives us a place to store the framerate as a timedelta
        timelapse.add_argument('--framerate-delta', type=timedelta, default=None, help= argparse.SUPPRESS)

        general = parser.add_argument_group('General', 'Miscellaneous parameters')
        general.add_argument('--loglevel', type=str,
                             help='Set the log level.')
        general.add_argument('--save-config', action='store_true', help='Save config to jsonfile and exit.')
        general.add_argument('--nframes', type=int,
                             help='Stop after writing this many frames. (useful for testing setup)')
        general.add_argument('--testframe', action='store_true',
                             help='Write a test frame with layout information.')

        # TODO: Should camera producer have an "add_arguents" function since it owns the Schedule object?
        parser = Schedule.add_arguments(parser, 'Timing')

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
class TimelapseApp():
    def __init__(self):
        self._config_loader = TimelapseConfig()
        self._config = self._config_loader.load_from_list()

        if self._config is None:
            raise Exception('Bad config')

        # placeholders for all the valid parameters
        self.width = self._config.width
        self.height = self._config.height
        self.outdir = self._config.outdir
        self.prefix = self._config.prefix
        self.show_name = self._config.show_name
        self.label_rgb = self._config.label_rgb
        self.nframes = self._config.nframes
        self.loglevel = self._config.loglevel
        self.save_config = self._config.save_config
        self.debug = self._config.debug
        self.testframe = self._config.testframe

        if not pl.it_is_time_to_die():
            self.process_config()
            self.out_queue = Queue()
            self._shutdown_event = threading.Event()

    def process_config(self):

        for k, v in self._config.__dict__.items():
            if k not in self.__dict__:
                logging.warning(f'Config attribute missing: {k}, config: {v}')
            self.__dict__[k] = v

        if self._config.zoom < 1.0:
            msg = f'Zoom must be 1.0 or greater. (set to: {self._config.zoom})'
            sys.stderr.write(msg + '\n')
            logging.error(msg)
            pl.die()

        if self.label_rgb is not None:
            (R,G,B) = self.label_rgb.split(',')
            self.label_rgb = BGR(int(R), int(G), int(B))

    def run(self):
        if pl.it_is_time_to_die():
            return
        ###
        # Create a Motion Consumer and Image Producer. Start them up.

        producer = None
        # create images using camera
        producer = CameraProducer(self.width, self.height, self._config.zoom, self._config.prefix,
                                  self._shutdown_event, self._config, out_queue=self.out_queue)
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
            time.sleep(1)
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

def oldmain():
    logging.info(f' --- Starting {pl.get_program_name()} ---')
    if not pl.create_pid_file():
        print(f'{pl.get_program_name()} might be running already. '
              f'If it is not, delete {pl.get_program_name()}.pid and try again')
        pl.die(1)

    timelapse_config = TimelapseConfig()
    config = timelapse_config.load_from_list()

    timelapse_config.dump_to_log(config)
    if config is None:
        pl.die(1)

    logging.debug(f'CMD: {" ".join(sys.argv)}')
    timelapse_config.dump_to_log(config)

    camera = Camera(config)

    nframes = 0
    start_time = datetime.now()
    logging.info(f'Starting Timelapse ({start_time.strftime("%Y/%m/%d %H:%M:%S")})')
    nextframe_time = None
    paused = False
    report_wait = timedelta(seconds=10)
    report_time = start_time + report_wait
    while not pl.it_is_time_to_die():
        now = datetime.now()

        if config.framerate:
            nextframe_time = now + config.framerate_delta
            logging.debug(f'nextframe_time: {nextframe_time}')

        if config.nframes and nframes > config.nframes:
            logging.info(f'Reached limit ({config.nframes} frames). Stopping.')
            break
        if now > report_time:
            elapsed = now - start_time
            FPS = nframes / elapsed.total_seconds()
            with open('/sys/class/thermal/thermal_zone0/temp') as f:
                temp = int(f.read().strip()) / 1000
            logging.info(f'Elapsed: {elapsed}, {nframes} frames. FPS = {FPS:5.2f} CPU Temp {temp}c')
            report_time = report_time + report_wait
        nframes += 1
        ts = now.strftime('%Y%m%d_%H%M%S.%f')
        fname_base = f'{config.prefix}_{ts}'
        new_name = f'{fname_base}.png'
        ats = now.strftime('%Y/%m/%d %H:%M:%S')
        annotatation = f'{ats}' if config.show_name else None
        new_path = os.path.join(config.outdir, new_name)
        logging.debug(f'About to snap')
        camera.file_capture(new_path)

        if nframes == 1 and config.testframe:
            logging.debug(f'Creating Test Frame')
            copy = cv2.imread(new_path)
            w = config.width
            h = config.height
            new_name_test = f'{fname_base}_test.png'

            for n in range(0, 10):
                y = int(h * n / 10)
                x = int(w * n / 10)
                cv2.line(copy, (0, y), (w, y), BLUE)
                cv2.line(copy, (x, 0), (x, h), BLUE)

            logging.info(f'TEST IMAGE: {new_name_test}')
            pl.annotate_frame(copy, annotatation, config)
            cv2.imwrite(os.path.join(config.outdir, new_name_test), copy)

        if config.framerate:
            if config.debug:
                logging.info(f'Pausing until {nextframe_time} (framerate:{config.framerate})')
            pause.until(nextframe_time)

if __name__ == '__main__':
    try:
        main()
        if pl.it_is_time_to_die():
            logging.info('Exiting: Graceful shutdown')
    except Exception as e:
        logging.exception(f'Unhandled Exception: {e}')
        pl.die(1)