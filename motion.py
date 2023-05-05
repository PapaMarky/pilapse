#! /usr/bin/env python3

import argparse
import json
import threading
from datetime import datetime, timedelta
from camera import Camera

from config import Config
import pilapse as pl
from queue import Queue
from threads import DirectoryProducer, CameraProducer, MotionConsumer

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
        logging.info(arglist)
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



# based on this:
# https://codedeepai.com/finding-difference-between-multiple-images-using-opencv-and-python/
def compare_images(original, new, config, fname_base):
    # original = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY)
    # new = cv2.cvtColor(new, cv2.COLOR_BGR2GRAY)

    #resize the images to make them smaller. Bigger image may take a significantly
    #more computing power and time
    motion_detected = False
    image_in = new.copy()
    scale = 1.0
    if config.shrinkto is not None:
        scale  = config.height / config.shrinkto
        original = imutils.resize(original.copy(), height = config.shrinkto)
        new = imutils.resize(new.copy(), height = config.shrinkto)

    sMindiff = int(config.mindiff / scale)
    sLeft = int(config.left / scale)
    sRight = int(config.right / scale)
    sTop = int(config.top / scale)
    sBottom = int(config.bottom / scale)

    #make a copy of original image so that we can store the
    #difference of 2 images in the same
    height, width = (config.height, config.width)
    oheight, owidth = (config.height, config.width)

    if height != oheight or width != owidth:
        logging.warning(f'SIZE MISSMATCH: original: {owidth} x {oheight}, new: {width} x {height}')
        return 0

    diff = original.copy()
    cv2.absdiff(original, new, diff)
    # 01 - diff
    if config.save_diffs and False:
        diff2 = diff.copy()
        diff2 = imutils.resize(diff2, config.height)
        diff_name = f'{fname_base}_01D.png'
        path = os.path.join(config.outdir, diff_name)
        logging.debug(f'Saving: {path}')
        cv2.imwrite(path, diff2)

    #converting the difference into grascale
    gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    # 02 - gray
    if config.save_diffs:
        gray2 = gray.copy()
        gray2 = imutils.resize(gray2, config.height)
        gray_name = f'{fname_base}_02G.png'
        path = os.path.join(config.outdir, gray_name)
        logging.debug(f'Saving: {path}')
        cv2.imwrite(path, gray2)

    #increasing the size of differences so we can capture them all
    #for i in range(0, 3):
    dilated = gray.copy()
    #for i in range(0, 3):
    #    dilated = cv2.dilate(dilated, None, iterations= i+ 1)

    dilated = cv2.dilate(dilated, None, iterations= config.dilation)
    # 03 - dilated
    if config.save_diffs:
        dilated2 = dilated.copy()
        dilated2 = imutils.resize(dilated2, config.height)
        dilated_name = f'{fname_base}_03D.png'
        path = os.path.join(config.outdir, dilated_name)
        logging.debug(f'Saving: {path}')
        cv2.imwrite(path, dilated2)

    #threshold the gray image to binarise it. Anything pixel that has
    #value more than 3 we are converting to white
    #(remember 0 is black and 255 is absolute white)
    #the image is called binarised as any value less than 3 will be 0 and
    # all values equal to and more than 3 will be 255
    # (T, thresh) = cv2.threshold(dilated, 3, 255, cv2.THRESH_BINARY)
    (T, thresh) = cv2.threshold(dilated, config.threshold, 255, cv2.THRESH_BINARY)

    # 04 - threshed
    if config.save_diffs:
        thresh2 = thresh.copy()
        thresh2 = imutils.resize(thresh2, config.height)
        thresh_name = f'{fname_base}_04T.png'
        path = os.path.join(config.outdir, thresh_name)
        logging.debug(f'Saving: {path}')
        cv2.imwrite(path, thresh2)

    # thresh = cv2.bitwise_not(thresh)
    # now we need to find contours in the binarised image
    # cnts = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    cnts = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_TC89_L1)
    cnts = imutils.grab_contours(cnts)

    copy = None
    def get_copy(copy):
        if copy is None:
            copy = new.copy()
        return copy

    # logging.debug(f'NEW SHAPE: {new.shape}')
    height, width, _ = new.shape
    if config.debug:
        copy = get_copy(image_in)
        cv2.rectangle(image_in, (0, config.top), (int(scale * width), config.bottom), RED)
    for c in cnts:
        # fit a bounding box to the contour
        (x, y, w, h) = cv2.boundingRect(c)
        sx = int(scale * x)
        sy = int(scale * y)
        sw = int(scale * w)
        sh = int(scale * h)

        if x + w > sRight:
            if config.debug:
                cv2.rectangle(copy, (sx, sy), (sx + sw, sy + sh), CYAN)
            continue
        if x < sLeft:
            if config.debug:
                cv2.rectangle(copy, (sx, sy), (sx + sw, sy + sh), CYAN)
            continue
        if y < sTop:
            if config.debug:
                cv2.rectangle(copy, (sx, sy), (sx + sw, sy + sh), CYAN)
            continue
        if y + h > sBottom:
            if config.debug:
                cv2.rectangle(copy, (sx, sy), (sx + sw, sy + sh), CYAN)
            continue
        if (w >= sMindiff or h >= sMindiff) and w < width and h < height:
            copy = get_copy(copy)
            if config.debug or config.show_motion:
                cv2.rectangle(copy, (sx, sy), (sx + sw, sy + sh), GREEN)
            motion_detected = True
        else:
            if config.debug:
                copy = get_copy(copy)
                cv2.rectangle(copy, (sx, sy), (sx + sw, sy + sh), MAGENTA)

    return copy, motion_detected

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
            self._queue = Queue()
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
            producer = DirectoryProducer(self.source_dir, 'png', self._queue, self._shutdown_event)
        else:
            # create images using camera
            producer = CameraProducer(self.width, self.height, self._config.zoom, self._config.prefix, self._config, self._queue, self._shutdown_event)
        consumer = MotionConsumer(self._config, self._queue, self._shutdown_event)

        consumer.start()
        producer.start()

        while True:
            logging.debug(f'waiting: producer alive? {producer.is_alive()}, consumer alive? {consumer.is_alive()}')
            if not consumer.is_alive() or not producer.is_alive():
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

                logging.info('Waiting for consumer...')
                try:
                    consumer.join(5.0)
                    if consumer.is_alive():
                        logging.warning('- Timed out, consumer is still alive.')
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
        logging.exception(e)

def oldmain():
    pl.create_pid_file()

    motion_config = MotionConfig()

    logging.info(f'Loading command line parameters')
    config = motion_config.load_from_list()
    motion_config.dump_to_log(config)


    #config = process_config(config)
    if config is None:
        pl.die(1)

    logging.debug(f'CMD: {" ".join(sys.argv)}')
    motion_config.dump_to_log(config)

    camera = Camera(config)
    original = None
    orig_name = ''
    new = None
    new_name = ''

    nframes = 0
    keepers = 0
    start_time = datetime.now()
    logging.info(f'Starting Motion Capture ({start_time.strftime("%Y/%m/%d %H:%M:%S")})')
    paused = False if config.run_from is None else True
    while not pl.it_is_time_to_die():
        now = datetime.now()
        if config.run_until is not None and not paused:
            if now.time() >= config.run_until_t:
                logging.info(f'Pausing because run_until: {config.run_until}')
                paused = True

        if paused:
            if now.time() <= config.run_from_t:
                logging.info(f'Ending pause because run_from: {config.run_from}')
                paused = False

        if paused:
            time.sleep(1)

        if config.nframes and nframes > config.nframes:
            logging.info(f'Reached limit ({config.nframes} frames). Stopping.')
            break
        if nframes > 0 and nframes % 100 == 0:
            elapsed = now - start_time
            FPS = nframes / elapsed.total_seconds()
            with open('/sys/class/thermal/thermal_zone0/temp') as f:
                temp = int(f.read().strip()) / 1000
            logging.info(f'Elapsed: {elapsed}, {nframes} frames. {keepers} saved. FPS = {FPS:5.2f} CPU Temp {temp}c')
        nframes += 1
        if config.stop_at and now > config.stop_at:
            logging.info(f'Shutting down due to "stop_at": {config.stop_at.strftime("%Y/%m/%d %H:%M:%S")}')
            pl.die()
        ts = now.strftime('%Y%m%d_%H%M%S.%f')
        fname_base = f'{config.prefix}_{ts}'
        new_name = f'{fname_base}_90.png' if config.save_diffs else f'{fname_base}.png'
        new_name_motion = f'{fname_base}_90M.png'
        ats = now.strftime('%Y/%m/%d %H:%M:%S')
        annotatation = f'{ats}' if config.show_name else None
        img_file_name = 'frame.png'
        new = camera.capture()

        if new is not None and original is None:
            if config.testframe:
                copy = new.copy()
                w = config.width
                h = config.height
                for n in range(0, 10):
                    y = int(h * n / 10)
                    x = int(w * n / 10)
                    color = RED if y < config.top or y > config.bottom else GREEN
                    cv2.line(copy, (0, y), (w, y), color)
                    color = RED if x < config.left else GREEN
                    cv2.line(copy, (x, 0), (x, h), color)
                cv2.line(copy, (0, config.top), (config.width, config.top), ORANGE)
                cv2.line(copy, (0, config.bottom), (config.width, config.bottom), ORANGE)
                cv2.rectangle(copy, (100, 100), (100 + config.mindiff, 100 + config.mindiff), WHITE)

                logging.info(f'TEST IMAGE: {new_name_motion}, top: {config.top}, bottom: {config.bottom}, left: {config.left}')
                pl.annotate_frame(copy, annotatation, config)
                cv2.imwrite(os.path.join(config.outdir, new_name_motion), copy)

        elif original is not None and new is not None:
            copy, motion_detected = compare_images(original, new, config, fname_base)

            if motion_detected:
                new_name = new_name_motion
                logging.info(f'MOTION DETECTED')

            if isinstance(copy, int):
                logging.info(f'Original: {orig_name}')
                logging.info(f'     New: {new_name}')
            elif copy is not None:
                logging.debug(f'{new_name}')
                keepers += 1
                pl.annotate_frame(copy, annotatation, config)
                cv2.imwrite(os.path.join(config.outdir, new_name), copy)
            elif config.all_frames:
                logging.debug(f'{new_name}')
                pl.annotate_frame(new, annotatation, config)
                cv2.imwrite(os.path.join(config.outdir, new_name), new)
        original = new
        orig_name = new_name

if __name__ == '__main__':
    try:
        main()
        if pl.it_is_time_to_die():
            logging.info('Exiting: Graceful shutdown')
    except Exception as e:
        logging.exception(f'Unhandled Exception: {e}')
        pl.die(1)