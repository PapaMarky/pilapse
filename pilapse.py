#! /usr/bin/env python3

import argparse
import signal
from datetime import datetime, timedelta
from config import Config

import cv2
import logging
import os
import sys
import time

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
    time.sleep(0.1)
    sys.exit(status)

logging.basicConfig(filename=f'{get_program_name()}.log',
#                    encoding='utf-8', # doesn't work in py 3.7
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

def process_config(myconfig):
    myconfig.bottom = int(myconfig.bottom * myconfig.height)
    myconfig.top = int(myconfig.top * myconfig.height)
    myconfig.left = int(myconfig.left * myconfig.width)
    myconfig.right = int(myconfig.right * myconfig.width)

    if myconfig.shrinkto is not None:
        logging.debug('shrinkto is set')
        if myconfig.shrinkto <= 1.0:
            logging.debug('shrink to is float')
            myconfig.shrinkto = myconfig.height * myconfig.shrinkto
        myconfig.shrinkto = int(myconfig.shrinkto)

    if '%' in myconfig.outdir:
        myconfig.outdir = datetime.strftime(datetime.now(), myconfig.outdir)
    os.makedirs(myconfig.outdir, exist_ok=True)

    if myconfig.stop_at is not None:
        logging.debug(f'Setting stop-at: {myconfig.stop_at}')
        (hour, minute, second) = myconfig.stop_at.split(':')
        myconfig.stop_at = datetime.now().replace(hour=int(hour), minute=int(minute), second=int(second), microsecond=0)

    if myconfig.run_from is not None:
        logging.debug(f'Setting run-until: {myconfig.run_from}')
        myconfig.__dict__['run_from_t'] = datetime.strptime(myconfig.run_from, '%H:%M:%S').time()

    if myconfig.run_until is not None:
        logging.debug(f'Setting run-until: {myconfig.run_until}')
        myconfig.__dict__['run_until_t'] = datetime.strptime(myconfig.run_until, '%H:%M:%S').time()

    if myconfig.framerate is not None:
        if not myconfig.all_frames:
            logging.warning(f'framerate set to {myconfig.framerate}, but all-frames not set. Ignoring framerate.')
            myconfig.framerate = 0
        else:
            myconfig.framerate_delta = timedelta(seconds=myconfig.framerate)
            myconfig.nomotion = True

    if myconfig.label_rgb is not None:
        (R,G,B) = myconfig.label_rgb.split(',')
        myconfig.label_rgb = BGR(int(R), int(G), int(B))

    return myconfig


def annotate_frame(image, annotaton, config):
    if annotaton:
        text_height = 10
        pos = (text_height, 2 * text_height)
        font = cv2.FONT_HERSHEY_SIMPLEX
        size, baseline = cv2.getTextSize(annotaton, font, 1, 3)
        scale = text_height / size[1]
        color = config.label_rgb if config.label_rgb is not None else ORANGE

        cv2.putText(image, annotaton, pos, font, scale, color=color)
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

