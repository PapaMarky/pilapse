#! /usr/bin/env python3

import argparse
import signal
from datetime import datetime, timedelta

import psutil

from config import Config

import cv2
import logging
import os
import sys
import time

# TODO Incorporate all of this "time to die" stuff into App class so it can have access to the shutdown event
time_to_die = False
def it_is_time_to_die():
    logging.debug(f'Is it time_to_die?: {time_to_die}')
    return time_to_die

def set_time_to_die():
    global time_to_die
    logging.debug('Setting "time_to_die"')
    time_to_die = True

def exit_gracefully(signum, frame):
    logging.info(f'SHUTTING {get_program_name()} DOWN due to {signal.Signals(signum).name}')
    set_time_to_die()

signal.signal(signal.SIGINT, exit_gracefully)
signal.signal(signal.SIGTERM, exit_gracefully)

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
BLACK = BGR(0, 0, 0)

def get_program_name():
    name = os.path.basename(sys.argv[0])
    s = name.split('.')
    if s[-1] == 'py':
        name = '.'.join(s[:-1])
    return name

def get_pid_file():
    return f'{get_program_name()}.pid'

def create_pid_file():
    pidfile = get_pid_file()
    if os.path.exists(pidfile):
        logging.error('PID file exists. Already running?')
        pid_in_use = True
        with open(pidfile) as f:
            pid = f.read().strip()
            try:
                pid = int(pid)
                if not psutil.pid_exists(pid):
                    logging.info(f'No process is using that PID ({pid}). Taking over the file')
                    pid_in_use = False
            except:
                logging.warning(f'PID in file is bad. Taking over the file.')
                pid_in_use = False
        if pid_in_use:
            return False
    with open(get_pid_file(), 'w') as pidout:
        pid = os.getpid()
        logging.info(f'saving PID ({pid}) in {pidfile}')
        pidout.write(f'{pid}')
    return True

def delete_pid_file():
    pidfile = get_pid_file()
    logging.info(f'Deleting PID file: {pidfile}')
    if os.path.exists(pidfile):
        logging.debug(f' - found {pidfile}')
        with open(pidfile) as f:
            pid = int(f.read())
            if os.getpid() != pid:
                logging.warning(f'PID file exists but contains "{pid}" (my pid is {os.getpid()})')
                return
        logging.debug(f' - deleting {pidfile}')
        os.remove(pidfile)

def die(status=0):
    logging.info(f'Time to die')
    delete_pid_file()
    time.sleep(0.1) # do not want this sleep to be interruptible
    sys.exit(status)

logfile = os.environ.get('LOGFILE')
if not logfile:
    logfile = f'{get_program_name()}.log'
if logfile == 'stdout':
    logfile = None

print(f'Logging to {logfile}')
logging.basicConfig(
    filename=logfile,
    level=logging.INFO,
    format='%(asctime)s|%(levelname)s|%(threadName)s|%(message)s'
    )


class PilapseConfig(Config):
    def __init__(self):
        super().__init__()

    def create_parser(self):
        parser = argparse.ArgumentParser(description='Capture a series of image frames. Includes functionality for '
                                                           'detecting motion and '
                                                           'creating a timelapse with motion detection')

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
        motion.add_argument('--save-diffs', action='store_true',
                            help='also save the diffed images for debugging')
        motion.add_argument('--threshold', type=int,
                            help='cut off threshold for detecting changes (0 - 255)',
                            default=25)
        motion.add_argument('--dilation', type=int, default=3,
                            help='Number of dilation iterations to perform')
        motion.add_argument('--debug', action="store_true",
                            help='Turn on debugging of motion analysis. Shows features too small or outside' \
                                 'region of interest')

        frame = parser.add_argument_group('Frame Setup', 'Parameters that control the generated frames')
        frame.add_argument('--width', '-W', type=int, help='width of each frame', default=640)
        frame.add_argument('--height', '-H', type=int, help='height of each frame', default=480)
        frame.add_argument('--show-name', action='store_true',
                           help='Write the file name (timestamp) on each frame')
        frame.add_argument('--label-rgb', type=str,
                           help='Set the color of the timestamp on each frame. '
                                'FORMAT: comma separated integers between 0 and 255, no spaces "R,G,B" ')
        frame.add_argument('--outdir', type=str,
                           help='directory where frame files will be written.',
                           default='./%Y%m%d')
        frame.add_argument('--prefix', type=str, default='snap',
                           help='Prefix frame filenames with this string')

        timelapse = parser.add_argument_group('Timelapse', 'Parameters that control timelapse')
        timelapse.add_argument('--all-frames', action='store_true',
                               help='Save all frames even when no motion is detected')
        timelapse.add_argument('--framerate', type=int, default=None,
                               help='When "all-frames" is set, "framerate" limits how often a new frame is taken. '
                                    'Int value. Units is seconds. EX. Setting framerate to "3" will take a frame every'
                                    '3 seconds. Defaults to 0 which means "as fast as you can" '
                                    'Setting framerate and all-frames imply "nomotion"')
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
        general.add_argument('--show-motion', action='store_true',
                             help='Highlight motion even when debug is false.')
        general.add_argument('--nomotion', action='store_true',
                             help='Disable motion detection. Use this, all-frames and framerate when making a timelapse')

        timing = parser.add_argument_group('Timing', 'Control when capture starts / stops')
        timing.add_argument('--stop-at', type=str,
                             help='Stop loop when time reaches "stop-at". Format: HH:MM:SS with HH in 24 hour format')
        timing.add_argument('--run-from', type=str,
                             help='Only run after this time of day. (Format: HH:MM:SS with HH in 24 hour format)')
        timing.add_argument('--run-until', type=str,
                             help='Only run until this time of day. (Format: HH:MM:SS with HH in 24 hour format)')
        return parser

    def load_from_list(self, arglist=None):
        config = super().load_from_list(arglist=arglist)
        self.dump_to_log(config)

        if config.save_config:
            self.dump_to_json(indent=2)
            die(1)

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


def annotate_frame(image, annotation, config, position='ul', text_size:float = 1.0):
    if annotation:
        text_height = int(config.height / 25 * text_size)
        thickness = int(config.height * 1/480 * text_size)
        if thickness < 1:
            thickness = 1

        font = cv2.FONT_HERSHEY_SIMPLEX
        text_size, baseline = cv2.getTextSize(annotation, font, 1, 3)

        image_h, image_w, _ = image.shape
        x = text_height
        y = 2 * text_height

        scale = text_height / text_size[1]
        color = config.label_rgb if config.label_rgb is not None else ORANGE

        logging.debug(f'pos: {position}, str: "{annotation}"')
        if position[1] in 'lL':
            x = text_height
        elif position[1] in 'rR':
            x = image_w - ((text_height + text_size[0]) * scale)

        if position[0] in 'uUtT':
            y = 2 * text_height
        elif position[0] in 'lLbB':
            y = image_h - 2 * text_height

        origin = (int(x), int(y))
        logging.debug(f'annotation origin for {position}: {origin}')
        # first write with greater thickness to create constrasting outline
        cv2.putText(image, annotation, origin, font, scale, WHITE, thickness=thickness + 2)
        cv2.putText(image, annotation, origin, font, scale, color, thickness=thickness)
        return text_height

def setup_camera(camera, config):
    logging.info('Setting up camera...')
    camera.resolution = (config.width, config.height)
    camera.rotation = 180
    camera.framerate = 80
    camera.exposure_mode = 'auto'
    camera.awb_mode = 'auto'
    # camera.zoom = (0.2, 0.3, 0.5, 0.5)
    time.sleep(2)
    logging.info(f'setup_camera completed: Camera Resolution: {camera.MAX_RESOLUTION}')

def snap_picture(camera, output='frame.png'):
    logging.debug(f'snap_picture({output})')
    (w, h) = camera.resolution
    # output = np.empty((w, h, 3), dtype=np.uint8)
    camera.capture(output)
    # camera.capture(output, 'rgb')
    # return output

