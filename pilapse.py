#! /usr/bin/env python3

import argparse
import json
import signal
from datetime import datetime, timedelta
from picamera import PiCamera

import cv2
import imutils
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

logging.basicConfig(filename='pilapse.log',
#                    encoding='utf-8', # doesn't work in py 3.7
                    level=logging.INFO,
                    format='%(asctime)s|%(levelname)s|%(message)s'
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
def snap_picture(camera):
    (w, h) = camera.resolution
    # output = np.empty((w, h, 3), dtype=np.uint8)
    camera.capture('frame.png')
    # camera.capture(output, 'rgb')
    # return output

def exit_gracefully(signum, frame):
    global time_to_die
    logging.info(f'SHUTTING DOWN due to {signal.Signals(signum).name}')
    time_to_die = True

signal.signal(signal.SIGINT, exit_gracefully)
signal.signal(signal.SIGTERM, exit_gracefully)

def main():
    pilapse_config = PilapseConfig()
    config = pilapse_config.load_from_list()

    pilapse_config.dump_to_log(config)
    config = process_config(config)
    if config is None:
        die(1)

    logging.debug(f'CMD: {" ".join(sys.argv)}')
    pilapse_config.dump_to_log(config)

    camera = PiCamera()
    setup_camera(camera, config)
    original = None
    orig_name = ''
    new = None
    new_name = ''

    nframes = 0
    keepers = 0
    start_time = datetime.now()
    logging.info(f'Starting Timelapse ({start_time.strftime("%Y/%m/%d %H:%M:%S")})')
    nextframe_time = None
    paused = False
    logging.info(f'paused: {paused}')
    while not time_to_die:
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
            continue

        if config.framerate:
            nextframe_time = now + config.framerate_delta

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
            die()
        ts = now.strftime('%Y%m%d_%H%M%S.%f')
        fname_base = f'{config.prefix}_{ts}'
        new_name = f'{fname_base}_90.png' if config.save_diffs else f'{fname_base}.png'
        new_name_motion = f'{fname_base}_90M.png'
        ats = now.strftime('%Y/%m/%d %H:%M:%S')
        annotatation = f'{ats}' if config.show_name else None
        snap_picture(camera)
        new = cv2.imread('frame.png')

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
                annotate_frame(copy, annotatation, config)
                cv2.imwrite(os.path.join(config.outdir, new_name_motion), copy)
            elif config.nomotion:
                annotate_frame(new, annotatation, config)
                cv2.imwrite(os.path.join(config.outdir, new_name), new)

        elif original is not None and new is not None:
            if config.nomotion:
                copy = new
                motion_detected = False
            else:
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
                annotate_frame(copy, annotatation, config)
                cv2.imwrite(os.path.join(config.outdir, new_name), copy)
            elif config.all_frames:
                logging.debug(f'{new_name}')
                annotate_frame(new, annotatation, config)
                cv2.imwrite(os.path.join(config.outdir, new_name), new)
        original = new
        orig_name = new_name

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