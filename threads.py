import argparse
import os
import queue
import threading
from datetime import datetime
from glob import glob
from queue import Queue
import logging
import watchdog.events
import watchdog.observers
import cv2
import imutils

import time

quit_command = '%quit%'


class FileImage():
    def __init__(self, path):
        self._path = path
        self._image = None

    @property
    def filename(self):
        return os.path.basename(self._path)

    @property
    def image(self):
        if self.image is None:
            self._image = cv2.imread(self._path)
        return self._image

class CameraImage():
    def __init__(self, image, prefix='snap', type='png'):
        self._image = image
        self._timestamp:datetime = datetime.now()
        self._prefix = prefix
        self._type = type

    @property
    def filename(self):
        return f'{self.base_filename}.{self._type}'

    @property
    def base_filename(self):
        return f'{self._prefix}_{self.timestamp_file}'
    @property
    def timestamp(self):
        return self.timestamp

    @property
    def timestamp_file(self):
        return self._timestamp.strftime('%Y%m%d_%H%M%S_%f')

    @property
    def timestamp_human(self):
        return self._timestamp.strftime('%Y/%m/%d %H:%M:%S')

    @property
    def image(self):
        return self._image

class ImageProducer(threading.Thread):
    def __init__(self, work_queue:Queue, shutdown_event:threading.Event):
        super().__init__(name='ImageProducer')
        self.queue:Queue = work_queue
        self.shutdown_event:threading.Event = shutdown_event

    def run(self) -> None:
        shutdown_event = self.shutdown_event
        logging.info(f'running ImageProducer ({self.shutdown_event})')
        while True:
            if shutdown_event.is_set():
                logging.info('Shutdown event received')
                break

            image = self.produce_image()
            if image is not None:
                self.queue.put(image)

    def produce_image(self) -> str:
        raise Exception('Base clase does not implement produce_image()')


class DirectoryProducer(ImageProducer):
    class Handler(watchdog.events.PatternMatchingEventHandler):
        def __init__(self, patterns:list, queue:queue.Queue):
            # Set the patterns for PatternMatchingEventHandler
            watchdog.events.PatternMatchingEventHandler.__init__(self, patterns=patterns,
                                                                 ignore_directories=True,
                                                                 case_sensitive=True)
            self.queue = queue

        def on_created(self, event):
            # logging.info(f"Watchdog received created event - {event.src_path}")
            self.queue.put(event.src_path)

    def __init__(self, dirpath, ext, work_queue:Queue, shutdown_event:threading.Event):
        super().__init__(work_queue, shutdown_event)
        logging.info(f'DirectoryProducer({dirpath}, {ext}, {work_queue}, {shutdown_event})')
        self.dirpath = dirpath
        self.extension = ext
        self.new_file_queue:Queue = Queue()
        self.handler = self.Handler([f'*.{ext}'], self.new_file_queue)
        self.observer = watchdog.observers.Observer()
        self.observer.schedule(self.handler, path=self.dirpath, recursive=False)

    def run(self) -> None:
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
            self.queue.put(FileImage(file))
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
                        self.queue.put(image)
                        logging.info(f'First New File: {image.filename}')
                        # if this file isn't in the existing files, we can deallocate that list (we are past the end)
                        self.existing_files = []
                        look_for_dups = False
                    else:
                        # logging.info(f'Dup File: {image}')
                        pass
                else:
                    self.queue.put(image)
                    logging.info(f'New File: {image.filename}')


from camera import Camera
class CameraProducer(ImageProducer):
    def __init__(self, width, height, work_queue, shutdown_event):
        super().__init__(work_queue, shutdown_event)
        self.setName('CameraProducer')
        self.width = width
        self.height = height
        self.camera = Camera(width, height)
        time.sleep(2)

    def produce_image(self) -> str:
        img = CameraImage(self.camera.capture())
        logging.info(f'captured {img.base_filename}')
        self.queue.put(img)

class ImageConsumer(threading.Thread):
    def __init__(self, queue:queue.Queue, shutdown_event:threading.Event):
        super().__init__()
        self._queue = queue
        self._shutdown_event = shutdown_event

    def run(self) -> None:
        while True:
            if self._shutdown_event.is_set():
                logging.warning(f'shutdown event is set')
                n = self._queue.qsize()
                if self._queue.empty():
                    logging.info('Queue is empty. Shutting down')
                    break
                logging.warning(f'Shutting down, but queue not empty')
            if not self._queue.empty():
                image = self._queue.get()
                if image == quit_command:
                    return
                self.consume_image(image)

    def consume_image(self, image):
        logging.info(f'Consuming {image.filename}')

class MotionConsumer(ImageConsumer):
    def __init__(self, config, queue, shutdown_event):
        super().__init__(queue, shutdown_event)
        self.setName('MotionConsumer')
        self.config = config
        self.current_image:CameraImage = None
        self.previous_image:CameraImage = None
        self.count = 0

    def consume_image(self, image):
        self.count += 1
        self.previous_image = self.current_image
        self.current_image = image
        logging.info(f'consume image: {image.filename}')
        if self.previous_image is not None and self.current_image is not None:
            img_out, motion_detected = self.compare_images()
            if motion_detected:
                logging.info('Motion Detected')
            else:
                logging.info('No Motion Detected')

    def compare_images(self):
        # original = cv2.cvtColor(original, cv2.COLOR_BGR2GRAY)
        # new = cv2.cvtColor(new, cv2.COLOR_BGR2GRAY)
        original = self.previous_image.image
        new = self.current_image.image
        config = self.config
        fname_base = self.current_image.base_filename
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

    def xxxcompare_images(self):
        pass
