import argparse
import shutil
import subprocess
from copy import copy
import os
import queue
import re
import threading
from datetime import datetime, timedelta
from glob import glob
from queue import Queue
import logging

import psutil
import watchdog.events
import watchdog.observers
import cv2
import imutils
import pilapse as pl

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

GIG = 1024 * 1024 * 1024
class Image():

    timestamp_pattern = '%Y%m%d_%H%M%S.%f'
    def __init__(self, path=None, image=None, type='png', prefix=f'frame'):
        self._path = path
        self._image = image
        self._prefix = prefix
        self._type:str = type
        self._timestamp:datetime = datetime.now()

    @property
    def filepath(self):
        return self._path


    @property
    def timestamp_file(self):
        return self._timestamp.strftime(self.timestamp_pattern)

    @property
    def base_filename(self):
        return f'{self._prefix}_{self.timestamp_file}'

    @property
    def filename(self):
        return f'{self.base_filename}.{self._type}'
    @property
    def timestamp(self):
        return self._timestamp

    @property
    def timestamp_human(self):
        return self._timestamp.strftime('%Y/%m/%d %H:%M:%S')

    @property
    def image(self):
        return self._image

    @property
    def type(self):
        return self._type

class FileImage(Image):
    def __init__(self, path):
        """
        Create a File Based Image
        :param path: full path to the image file. Expected format: "PATH/PREFIX_YYYYMMDD_HHMMSS.ssssss.TYPE"
        """
        filename = os.path.basename(path)
        # groups: 1 = prefix, 2 = timestamp, 3 = type (extension)
        regex = r'([^_]+?)_([0-9]+?_[0-9]+?\.[0-9]+?)\.(.+)'
        m = re.match(regex, os.path.basename(filename))
        # 20230429/picam001_20230429_192140.054980.png
        if not m:
            raise Exception(f'Bad filename format: {path}')
        super().__init__(path=path, type=m.group(3) )
        self._timestamp = datetime.strptime(m.group(2), self.timestamp_pattern)
        self._prefix = m.group(1)

    @property
    def filename(self):
        return os.path.basename(self._path)

    @property
    def image(self):
        if self.image is None:
            self._image = cv2.imread(self._path)
        return self._image

class CameraImage(Image):
    def __init__(self, image, prefix='snap', type='png'):
        super().__init__(image=image, prefix=prefix, type=type)

class PilapseThread(threading.Thread):
    def __init__(self, name='PL_Thread'):
        super().__init__(name=name)
        self.excecption:Exception = None

    def do_work(self):
        pass
    def run(self):
        try:
            self.do_work()
        except Exception as e:
            logging.exception(e)
            self.excecption = e

    def signal_shutdown(self):
        self._shutdown_event.set()

    def join(self):
        threading.Thread.join(self)
        # Since join() returns in caller thread
        # we re-raise the caught exception
        # if any was caught
        if self.excecption:
            raise self.excecption

class ImageProducer(PilapseThread):
    def __init__(self, work_queue:Queue, shutdown_event:threading.Event, name='ImageProducer'):
        super().__init__(name=name)
        self.out_queue:Queue = work_queue
        self.shutdown_event:threading.Event = shutdown_event

    def log_status(self):
        pass

    def preproduce(self):
        pass

    def do_work(self) -> None:
        shutdown_event = self.shutdown_event
        logging.info(f'running ImageProducer ({self.shutdown_event})')
        while True:
            if shutdown_event.is_set():
                logging.info('Shutdown event received')
                break
            if self.preproduce():
                image = self.produce_image()
                if image is not None:
                    self.out_queue.put(image)

    def produce_image(self) -> str:
        raise Exception('Base clase does not implement produce_image()')


class DirectoryProducer(ImageProducer):
    class Handler(watchdog.events.PatternMatchingEventHandler):
        def __init__(self, patterns:list, out_queue:queue.Queue):
            # Set the patterns for PatternMatchingEventHandler
            watchdog.events.PatternMatchingEventHandler.__init__(self, patterns=patterns,
                                                                 ignore_directories=True,
                                                                 case_sensitive=True)
            self.queue = out_queue

        def on_created(self, event):
            # logging.info(f"Watchdog received created event - {event.src_path}")
            self.queue.put(event.src_path)

    def __init__(self, dirpath, ext, work_queue:Queue, shutdown_event:threading.Event):
        super().__init__(work_queue, shutdown_event, name="DirectoryProducer")
        logging.info(f'DirectoryProducer({dirpath}, {ext}, {work_queue}, {shutdown_event})')
        self.dirpath = dirpath
        self.extension = ext
        self.new_file_queue:Queue = Queue()
        self.handler = self.Handler([f'*.{ext}'], self.new_file_queue)
        self.observer = watchdog.observers.Observer()
        self.observer.schedule(self.handler, path=self.dirpath, recursive=False)

    def do_work(self) -> None:
        if self.shutdown_event.is_set():
            logging.info('Shutdown event received at beginning of run')
            return
        #  Load the exiting files, start the observer
        logging.info(f'Directory producer starting')
        self.observer.setName('Observer')
        self.observer.start()
        self.existing_files = glob(f'{self.dirpath}/*.{self.extension}')
        self.existing_files.sort()
        for file in self.existing_files:
            if self.shutdown_event.is_set():
                logging.info('Shutdown event received while processing existing files')
                break
            logging.info(f'Existing File: {file}')
            self.out_queue.put(FileImage(file))
        look_for_dups = True
        while True:
            if self.shutdown_event.is_set():
                logging.info('Shutdown event received while processing new files')
                break
            if not self.new_file_queue.empty():
                # get the new image, make sure we don't have it already, put it in the outgoing queue
                image = FileImage(self.new_file_queue.get())
                if look_for_dups:
                    if not image in self.existing_files:
                        self.out_queue.put(image)
                        logging.info(f'First New File: {image.filename}')
                        # if this file isn't in the existing files, we can deallocate that list (we are past the end)
                        self.existing_files = []
                        look_for_dups = False
                    else:
                        # logging.info(f'Dup File: {image}')
                        pass
                else:
                    self.out_queue.put(image)
                    logging.info(f'New File: {image.filename}')


from camera import Camera
class CameraProducer(ImageProducer):
    # TODO Camera producer should be aware of
    #    - "pause" due to run_from / run_until
    #    - stop_at
    #    - nframes
    # or move that control into app?
    def __init__(self, width, height, zoom, prefix, config, work_queue, shutdown_event):
        super().__init__(work_queue, shutdown_event, name='CameraProducer')
        self.width = width
        self.height = height
        self.prefix = prefix
        self.config = copy(config)
        self.camera = Camera(width, height, zoom)

        self.paused = False if self.config.run_from is None else True

        if self.config.stop_at is not None:
            logging.debug(f'Setting stop-at: {self.config.stop_at}')
            (hour, minute, second) = self.config.stop_at.split(':')
            self.config.stop_at = datetime.now().replace(hour=int(hour), minute=int(minute), second=int(second), microsecond=0)

        if self.config.run_from is not None:
            logging.debug(f'Setting run-until: {self.config.run_from}')
            self.config.run_from_t = datetime.strptime(self.config.run_from, '%H:%M:%S').time()

        if self.config.run_until is not None:
            logging.debug(f'Setting run-until: {self.config.run_until}')
            self.config.run_until_t = datetime.strptime(self.config.run_until, '%H:%M:%S').time()
        self.now = datetime.now()

        time.sleep(2) # this is really so the camera can warm up

    def get_camera_model(self):
        return self.camera.model()

    def log_status(self):
        if self.now > self.report_time:
            elapsed = self.now - self.start_time
            elapsed_str = str(elapsed).split('.')[0]
            FPS = self.nframes / elapsed.total_seconds()
            with open('/sys/class/thermal/thermal_zone0/temp') as f:
                temp = int(f.read().strip()) / 1000
            p = subprocess.run(['vcgencmd', 'measure_temp'], capture_output=True)
            t = p.stdout.decode()
            r = r'^temp=([.0-9]+)'
            m = re.match(r, t)
            t = m.group(1) if m is not None else ''

            # logging.info(f'# {os.uname()[1]}: CPU {psutil.cpu_percent()}%, mem {psutil.virtual_memory().percent}%, TEMP CPU: {temp:.1f}C GPU: {t}C')
            logging.info(f'  - Elapsed: {elapsed_str} frames: {self.nframes} saved: {self.keepers} FPS: {FPS:.2f} Paused: {self.paused}')
            self.report_time = self.report_time + self.report_wait

    def check_run_until(self):
        # Manage run_from and run_until
        current_time = self.now.time()
        if self.config.run_until is not None and not self.paused:
            logging.info(f'Run from {self.config.run_from} until {self.config.run_until}')

            if current_time >= self.config.run_until_t or current_time <= self.config.run_from_t:
                logging.info(f'Pausing because outside run time: from {self.config.run_from} until {self.config.run_until}')
                self.paused = True

        if self.paused:
            logging.debug(f'Paused, check the time. now: {self.now.time()}, run from: {self.config.run_from}')
            if current_time >= self.config.run_from_t and current_time <= self.config.run_until_t:
                logging.info(f'Ending pause because inside run time: from {self.config.run_from} until {self.config.run_until}')
                self.paused = False

        if self.paused:
            time.sleep(1)
            return False
        return True

    def check_stop_at(self):
        if self.config.stop_at and self.now > self.config.stop_at:
            logging.info(f'Shutting down due to "stop_at": {self.config.stop_at.strftime("%Y/%m/%d %H:%M:%S")}')
            self.shutdown_event.set()
            return False
        return True

    def preproduce(self):
        self.now = datetime.now()
        if not self.check_run_until():
            logging.info(f'Run Until Check Failed')
            return False

        if not self.check_stop_at():
            logging.info(f'Stop At Check Failed. Shutting down')
            self.shutdown_event.set()
            return False

        return True
    def produce_image(self) -> str:
        if not self.shutdown_event.is_set():
            img = CameraImage(self.camera.capture(), prefix=self.prefix, type='png')
            logging.debug(f'captured {img.base_filename}')
            self.out_queue.put(img)

class ImageConsumer(PilapseThread):
    def __init__(self, config:argparse.Namespace, queue:queue.Queue, shutdown_event:threading.Event):
        super().__init__()
        self.config = copy(config)
        self._queue = queue
        self._shutdown_event = shutdown_event
        self.nframes = 0
        self.keepers = 0
        self.start_time = datetime.now()
        self.now = self.start_time
        self.paused = False

        self.report_wait = timedelta(seconds=30)
        self.report_time = self.start_time + self.report_wait

        self.outdir = self.config.outdir
        if '%' in self.outdir:
            self.outdir = datetime.strftime(datetime.now(), self.config.outdir)
        os.makedirs(self.outdir, exist_ok=True)

        self.current_time = self.now

    def set_outdir(self):
        if '%' in self.config.outdir and self.current_time.minute != self.now.minute:
            logging.debug(f'Time (minute) changed, checking outdir')
            self.current_time = self.now
            new_outdir = datetime.strftime(datetime.now(), self.config.outdir)
            if new_outdir != self.outdir:
                self.outdir = new_outdir
                os.makedirs(self.outdir, exist_ok=True)
                logging.info(f'New outdir: {self.outdir}')

    def preconsume(self):
            """
            Called in the run loop prior to consuming the image. If this returns False, consume_image is not called and
            the loop continues
            :return:
            """
            return True

    def log_status(self):
        if self.now > self.report_time:
            elapsed = self.now - self.start_time
            elapsed_str = str(elapsed).split('.')[0]
            FPS = self.nframes / elapsed.total_seconds()
            with open('/sys/class/thermal/thermal_zone0/temp') as f:
                temp = int(f.read().strip()) / 1000
            p = subprocess.run(['vcgencmd', 'measure_temp'], capture_output=True)
            t = p.stdout.decode()
            r = r'^temp=([.0-9]+)'
            m = re.match(r, t)
            t = m.group(1) if m is not None else ''

            d = shutil.disk_usage(self.outdir)
            disk_usage = d.used / d.total * 100.0
            logging.info(f'# {os.uname()[1]}: CPU {psutil.cpu_percent()}%, mem {psutil.virtual_memory().percent}% disk: {disk_usage:.1f}% TEMP CPU: {temp:.1f}C GPU: {t}C')
            logging.info(f'  - Elapsed: {elapsed_str} frames: {self.nframes} saved: {self.keepers} FPS: {FPS:.2f} Paused: {self.paused} Q: {self._queue.qsize()}')
            self.report_time = self.report_time + self.report_wait

    def do_work(self) -> None:
        self.start_time = datetime.now()
        logging.info(f'Starting Motion Capture ({self.start_time.strftime("%Y/%m/%d %H:%M:%S")})')
        logging.info(f'Config: {self.config}')
        self.paused = False if self.config.run_from is None else True
        force_consume = False
        while True:
            # Have we received shutdown event?
            if self._shutdown_event.is_set():
                logging.warning(f'shutdown event is set')
                if self._queue.empty() or (self.config.nframes is not None and self.nframes >= self.config.nframes):
                    logging.info('Queue is empty. Shutting down')
                    break
                logging.warning(f'Trying to shutdown, but queue not empty: {self._queue.qsize()}')
                force_consume = True

            self.now = datetime.now()
            self.set_outdir()

            self.log_status()
            if not self._queue.empty():
                if self.preconsume() or force_consume:
                    image = self._queue.get()
                    self.consume_image(image)
                else:
                    logging.debug(f'preconsume returned false.')

    def consume_image(self, image):
        logging.info(f'Consuming {image.filename}')

class MotionConsumer(ImageConsumer):
    def __init__(self, config, queue, shutdown_event):
        super().__init__(config, queue, shutdown_event)
        self.setName('MotionConsumer')
        self.current_image:CameraImage = None
        self.previous_image:CameraImage = None
        self.count = 0
        self.paused = False

        if self.config.stop_at is not None:
            logging.debug(f'Setting stop-at: {self.config.stop_at}')
            (hour, minute, second) = self.config.stop_at.split(':')
            self.config.stop_at = datetime.now().replace(hour=int(hour), minute=int(minute), second=int(second), microsecond=0)

        if self.config.run_from is not None:
            logging.debug(f'Setting run-until: {self.config.run_from}')
            self.config.run_from_t = datetime.strptime(self.config.run_from, '%H:%M:%S').time()

        if self.config.run_until is not None:
            logging.debug(f'Setting run-until: {self.config.run_until}')
            self.config.run_until_t = datetime.strptime(self.config.run_until, '%H:%M:%S').time()

        if self.config.label_rgb is not None:
            (R,G,B) = self.config.label_rgb.split(',')
            self.config.label_rgb = BGR(int(R), int(G), int(B))

    def check_run_until(self):
        # TODO should be in the producer thread. If the producer stops producing,
        # the consumer will stop consuming

        # Manage run_from and run_until
        current_time = self.now.time()
        if self.config.run_until is not None and not self.paused:
            logging.debug(f'Run from {self.config.run_from} until {self.config.run_until}')

            if current_time >= self.config.run_until_t or current_time <= self.config.run_from_t:
                logging.info(f'Starting pause because outside run time: from {self.config.run_from} until {self.config.run_until}')
                self.paused = True

        if self.paused:
            logging.debug(f'Paused, check the time. now: {self.now.time()}, run from: {self.config.run_from}')
            if current_time >= self.config.run_from_t and current_time <= self.config.run_until_t:
                logging.info(f'Ending pause because inside run time: from {self.config.run_from} until {self.config.run_until}')
                self.paused = False

        if self.paused:
            time.sleep(1)
            return False
        return True

    def check_stop_at(self):
        if self.config.stop_at and self.now > self.config.stop_at:
            logging.info(f'Shutting down due to "stop_at": {self.config.stop_at.strftime("%Y/%m/%d %H:%M:%S")}')
            self.signal_shutdown()
            return False
        return True

    def preconsume(self):
        # If nframes is set, have we exceeded it?
        if self.config.nframes and self.nframes > self.config.nframes:
            logging.info(f'Reached limit ({self.config.nframes} frames). Stopping.')
            self.signal_shutdown()
            return False

        if not self.check_run_until():
            return False

        if not self.check_stop_at():
            self.signal_shutdown()
            return False
        return True

    def adjust_config(self, w, h):
        self.config.width = w
        self.config.height = h
        self.config.bottom = int(self.config.bottom * h)
        self.config.top = int(self.config.top * h)
        self.config.left = int(self.config.left * w)
        self.config.right = int(self.config.right * w)

    def consume_image(self, image):

        self.nframes += 1
        self.previous_image = self.current_image
        self.current_image = image

        logging.debug(f'Consuming image: {image.filename}')
        fname_base = self.current_image.base_filename
        new_name = f'{fname_base}_90.{self.current_image.type}' if self.config.save_diffs else f'{fname_base}.{self.current_image.type}'
        new_name_motion = f'{fname_base}_90M.{self.current_image.type}'
        ats = self.now.strftime('%Y/%m/%d %H:%M:%S')
        annotatation = f'{ats}' if self.config.show_name else None

        if self.current_image is not None and self.previous_image is None:
            # There are some config items that need to be adjusted once we know the height and width of the images.
            # In the case where we are reading from files, until we process the first image we don't know the sizes
            h, w, _ = self.current_image.image.shape
            logging.debug(f'Image Size: ({w} x {h})')
            self.adjust_config(w, h)
            if self.config.testframe:
                copy = self.current_image.image.copy()
                logging.debug(f'drawing lines: top: {self.config.top}, bottom: {self.config.bottom}')
                for n in range(0, 10):
                    y = int(h * n / 10)
                    x = int(w * n / 10)
                    color = RED if y < self.config.top or y > self.config.bottom else GREEN
                    cv2.line(copy, (0, y), (w, y), color)
                    color = RED if x < self.config.left else GREEN
                    cv2.line(copy, (x, 0), (x, h), color)
                cv2.line(copy, (0, self.config.top), (w, self.config.top), ORANGE)
                cv2.line(copy, (0, self.config.bottom), (w, self.config.bottom), ORANGE)
                cv2.line(copy, (self.config.left, 0), (self.config.left, h), ORANGE)
                cv2.line(copy, (self.config.right, 0), (self.config.right, h), ORANGE)
                cv2.rectangle(copy, (100, 100), (100 + self.config.mindiff, 100 + self.config.mindiff), WHITE)

                pl.annotate_frame(copy, annotatation, self.config)
                path = os.path.join(self.outdir, new_name_motion)
                path = path.replace('90M', '90MT')
                logging.debug(f'Writing Test Image: {path}')
                cv2.imwrite(path, copy)
        elif self.previous_image is not None and self.current_image is not None:
                img_out, motion_detected = self.compare_images()
                if motion_detected:
                    new_name = new_name_motion
                    logging.info(f'Motion Detected: {new_name}')
                else:
                    # logging.debug('No Motion Detected')
                    pass

                if img_out is not None:
                    logging.debug(f'{new_name}')
                    self.keepers += 1
                    pl.annotate_frame(img_out, annotatation, self.config)
                    path = os.path.join(self.outdir, new_name)
                    logging.debug(f'Writing Motion frame: {path}')
                    cv2.imwrite(path, img_out)
                elif self.config.all_frames:
                    path = os.path.join(self.outdir, new_name)
                    logging.debug(f'Writing all frames: {path}')
                    pl.annotate_frame(self.current_image.image, annotatation, self.config)
                    cv2.imwrite(path, self.current_image.image)

    def compare_images(self):
        original = self.previous_image.image
        new = self.current_image.image

        config = self.config
        fname_base = self.current_image.base_filename
        #resize the images to make them smaller. Bigger image may take a significantly
        #more computing power and time
        motion_detected = False
        image_in = new.copy()

        ### EXPERIMENT: Try blurring the source images to reduce lots of small movement from registering
        #   (EX wind and trees)
        if True:
            original = cv2.blur(original, (10, 10))
            new = cv2.blur(new, (10, 10))
            if config.save_diffs:
                blur_name = f'{fname_base}_00B.png'
                path = os.path.join(self.outdir, blur_name)
                logging.info(f'Saving {path}')
                cv2.imwrite(path, new)


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
        if config.save_diffs:
            diff2 = diff.copy()
            diff2 = imutils.resize(diff2, config.height)
            diff_name = f'{fname_base}_01D.png'
            path = os.path.join(self.outdir, diff_name)
            logging.debug(f'Saving: {path}')
            cv2.imwrite(path, diff2)

        #converting the difference into grascale
        gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        # 02 - gray
        if config.save_diffs:
            gray2 = gray.copy()
            gray2 = imutils.resize(gray2, config.height)
            gray_name = f'{fname_base}_02G.png'
            path = os.path.join(self.outdir, gray_name)
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
            path = os.path.join(self.outdir, dilated_name)
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
            path = os.path.join(self.outdir, thresh_name)
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
                copy = image_in.copy()
            return copy

        # logging.debug(f'NEW SHAPE: {new.shape}')
        height, width, _ = new.shape
        if config.debug:
            copy = get_copy(image_in)
            cv2.rectangle(image_in, (sLeft, sTop), (sRight, sBottom), RED)
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
