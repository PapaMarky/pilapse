#! /usr/bin/env python3

import argparse
import json
import signal
from datetime import datetime, timedelta
from picamera import PiCamera

from config import Config

import cv2
import logging
import os
import sys
import time
import pause

time_to_die = False

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


logging.basicConfig(filename='timelapse.log',
#                    encoding='utf-8', # doesn't work in py 3.7
                    level=logging.INFO,
                    format='%(asctime)s|%(levelname)s|%(message)s'
                    )


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
        timelapse.add_argument('--framerate', type=int, default=None,
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

        timing = parser.add_argument_group('Timing', 'Control when capture starts / stops')
        timing.add_argument('--stop-at', type=str,
                             help='Stop loop when time reaches "stop-at". Format: HH:MM:SS with HH in 24 hour format')
        timing.add_argument('--run-from', type=str,
                             help='Only run after this time of day. (Format: HH:MM:SS with HH in 24 hour format)')
        timing.add_argument('--run-until', type=str,
                             help='Only run until this time of day. (Format: HH:MM:SS with HH in 24 hour format)')
        return parser

    def load_from_list(self, arglist=None):
        logging.info('loading config from list:')
        logging.info(arglist)
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
            die()

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

    if '%' in myconfig.outdir:
        myconfig.outdir = datetime.strftime(datetime.now(), myconfig.outdir)
    os.makedirs(myconfig.outdir, exist_ok=True)

    if myconfig.stop_at is not None:
        logging.debug(f'Setting stop-at: {myconfig.stop_at}')
        (hour, minute, second) = myconfig.stop_at.split(':')
        myconfig.stop_at = datetime.now().replace(hour=int(hour), minute=int(minute), second=int(second), microsecond=0)

    if myconfig.run_from is not None:
        logging.debug(f'Setting run_from: {myconfig.run_from}')
        myconfig.__dict__['run_from_t'] = datetime.strptime(myconfig.run_from, '%H:%M:%S').time()

    if myconfig.run_until is not None:
        logging.debug(f'Setting run-until: {myconfig.run_until}')
        myconfig.__dict__['run_until_t'] = datetime.strptime(myconfig.run_until, '%H:%M:%S').time()

    if myconfig.framerate is not None:
        myconfig.framerate_delta = timedelta(seconds=myconfig.framerate)

    if myconfig.label_rgb is not None:
        (R,G,B) = myconfig.label_rgb.split(',')
        myconfig.label_rgb = BGR(int(R), int(G), int(B))

    return myconfig

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

def annotate_frame(image, annotaton, config):
    if annotaton:
        text_height = 10
        pos = (text_height, 2 * text_height)
        font = cv2.FONT_HERSHEY_SIMPLEX
        size, baseline = cv2.getTextSize(annotaton, font, 1, 3)
        scale = text_height / size[1]
        color = config.label_rgb if config.label_rgb is not None else ORANGE

        cv2.putText(image, annotaton, pos, font, scale, color=color)
        if config.debug:
            t = f'({config.width:4} x {config.height:4})  ({config.top:4}, {config.left}) - ({config.bottom:4}, {config.right}), mindiff: {config.mindiff} shrinkto: {config.shrinkto}'
            pos = (text_height, int(config.height - 1.5 * text_height))
            cv2.putText(image, t, pos, font, scale, color=color)
def snap_picture(camera, output='frame.png'):
    logging.debug(f'snap_picture({output})')
    (w, h) = camera.resolution
    # output = np.empty((w, h, 3), dtype=np.uint8)
    camera.capture(output)
    # camera.capture(output, 'rgb')
    # return output

def die(status=0):
    logging.info(f'Time to die')
    sys.exit(status)

def exit_gracefully(signum, frame):
    global time_to_die
    logging.info(f'SHUTTING DOWN due to {signal.Signals(signum).name}')
    time_to_die = True

signal.signal(signal.SIGINT, exit_gracefully)
signal.signal(signal.SIGTERM, exit_gracefully)

def main():
    pid = os.getpid()
    pidfile = f'timelapse.pid'
    with open(pidfile, 'w') as pidout:
        print(f'saving PID in {pidfile}')
        pidout.write(f'{pid}')
    timelapse_config = TimelapseConfig()
    config = timelapse_config.load_from_list()

    timelapse_config.dump_to_log(config)
    config = process_config(config)
    if config is None:
        die(1)

    logging.debug(f'CMD: {" ".join(sys.argv)}')
    timelapse_config.dump_to_log(config)

    camera = PiCamera()
    setup_camera(camera, config)

    nframes = 0
    start_time = datetime.now()
    logging.info(f'Starting Timelapse ({start_time.strftime("%Y/%m/%d %H:%M:%S")})')
    nextframe_time = None
    paused = False
    report_wait = timedelta(seconds=10)
    report_time = start_time + report_wait
    while not time_to_die:
        now = datetime.now()
        logging.debug(f'-loop {now}: paused: {paused}, run_until; {config.run_until}')
        if config.run_until is not None and not paused:
            if now.time() >= config.run_until_t:
                logging.info(f'Pausing because run_until: {config.run_until}')
                paused = True

        if paused:
            if now.time() <= config.run_from_t:
                logging.info(f'Ending pause because run_from: {config.run_from}')
                paused = False

        if paused:
            pause_seconds = 1
            logging.debug(f'pausing {pause_seconds} second...')
            time.sleep(pause_seconds)

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
        if config.stop_at and now > config.stop_at:
            logging.info(f'Shutting down due to "stop_at": {config.stop_at.strftime("%Y/%m/%d %H:%M:%S")}')
            die()
        ts = now.strftime('%Y%m%d_%H%M%S.%f')
        fname_base = f'{config.prefix}_{ts}'
        new_name = f'{fname_base}.png'
        ats = now.strftime('%Y/%m/%d %H:%M:%S')
        annotatation = f'{ats}' if config.show_name else None
        new_path = os.path.join(config.outdir, new_name)
        logging.debug(f'About to snap')
        snap_picture(camera, new_path)

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
            annotate_frame(copy, annotatation, config)
            cv2.imwrite(os.path.join(config.outdir, new_name_test), copy)

        if config.framerate:
            if config.debug:
                logging.info(f'Pausing until {nextframe_time} (framerate:{config.framerate})')
            pause.until(nextframe_time)

if __name__ == '__main__':
    try:
        main()
        if time_to_die:
            logging.info('Exiting: Graceful shutdown')
    except Exception as e:
        logging.exception(f'Unhandled Exception: {e}')
        die(1)