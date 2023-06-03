import argparse
import shutil
import subprocess
import sys
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

import pilapse
import pilapse as pl


from config import Configurable
from system_resources import SystemResources

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

    timestamp_pattern:str = '%Y%m%d_%H%M%S.%f'
    def __init__(self, path:str=None, image=None, type:str='png', prefix:str=f'frame',
                 timestamp:datetime=None, suffix=''):
        self._path:str = path
        self._image:picamera.PiArrayOutput = image
        self._prefix:str = prefix
        self._type:str = type
        self._timestamp:datetime = timestamp if timestamp is not None else datetime.now()
        self._suffix:str = suffix

    def to_str(self):
        return f'path: {self.filepath}, timefile: {self.timestamp_file} base: {self.base_filename} ' \
               f'filename: {self.filename} type: {self.type}'

    @property
    def filepath(self) -> str:
        return self._path


    @property
    def timestamp_file(self):
        return self._timestamp.strftime(self.timestamp_pattern)

    @property
    def base_filename(self):
        filename = f'{self.timestamp_file}_{self._prefix}'
        if self._suffix:
            filename += f'_{self._suffix}'

        return filename

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
    def timestamp_long(self):
        return self._timestamp.strftime('%Y/%m/%d %H:%M:%S.%f')

    @property
    def image(self):
        return self._image

    @property
    def type(self):
        return self._type

class FileImage(Image):
    def __init__(self, path, image=None):
        """
        Create a File Based Image
        :param path: full path to the image file. Expected format: "PATH/PREFIX_YYYYMMDD_HHMMSS.ssssss.TYPE"
        """
        filename = os.path.basename(path)
        # groups: 2 = prefix, 1 = timestamp, 3 = type (extension)
        # regex = r'([^_]+?)_([0-9]+?_[0-9]+?\.[0-9]+?)(_.*?)?\.(.+)'
        regex = r'([0-9]+?_[0-9]+?\.[0-9]+?)_([^_]+?)(_.*?)?\.(.+)'
        m = re.match(regex, os.path.basename(filename))
        # 20230429/picam001_20230429_192140.054980.png
        # picam002_20230508_053200.835233.png
        # 20230526_144349.20090p2_picam001.png
        if not m:
            raise Exception(f'Bad filename format: {path}')
        super().__init__(path=path, type=m.group(4), prefix=m.group(2), suffix=m.group(3))
        self._timestamp = datetime.strptime(m.group(1), self.timestamp_pattern)
        self._image = image

    @property
    def filename(self):
        return os.path.basename(self._path)

    @property
    def image(self):
        if self._image is None:
            logging.debug(f'reading image from {self._path}')
            self._image = cv2.imread(self._path)
        return self._image

class CameraImage(Image):
    def __init__(self, image, prefix='snap', type='png', timestamp=None, suffix=''):
        super().__init__(image=image, prefix=prefix, suffix=suffix, type=type, timestamp=timestamp)
        self.data = None

    @property
    def camera_settings(self):
        return self.data

    def copy_camera_settings(self, settings):
        '''
        this is meant to be used when making a copy of a CameraImage (for processing, etc) so that we can
        keep the settings after working on the image
        :param settings:
        :return:
        '''
        self.data = settings

    def set_camera_data(self, shutter_speed, iso, aperture, awb_mode, meter_mode, exposure_mode,
                        analog_gain, digital_gain, awb_gains, lux):
        self.data = {
            'shutter-speed': shutter_speed,
            'iso': iso,
            'aperture': aperture,
            'awb-mode': awb_mode,
            'meter-mode': meter_mode,
            'exposure-mode': exposure_mode,
            'analog-gain': analog_gain,
            'digital-gain': digital_gain,
            'awb-gains': awb_gains,
            'lux': lux
        }

class PilapseThread(threading.Thread):
    def __init__(self, piname, shutdown_event:threading.Event, config:argparse.Namespace, **kwargs):
        super().__init__(group=None, target=None, name=None)
        self.setName(piname)
        logging.debug(f'PilapseThread init {self.name}')
        self.shutdown_event:threading.Event = shutdown_event
        self.config:argparse.Namespace = copy(config)
        self.excecption:Exception = None
        self.start_time:datetime = datetime.now()

        self.report_wait:timedelta = timedelta(seconds=30)
        self.report_time:datetime = self.start_time + self.report_wait
        self.now = datetime.now()

    def start_work(self):
        self.start_time = datetime.now()
        self.report_time:datetime = self.start_time + self.report_wait

    def do_work(self):
        logging.warning(f'PilapseThread: do_work for {self.name}')
        pass

    def run(self):
        try:
            self.do_work()
        except Exception as e:
            logging.error(f'Exception in Thread: {self.name}')
            logging.exception(e)
            self.excecption = e

    def signal_shutdown(self):
        self.shutdown_event.set()

    def join(self):
        threading.Thread.join(self)
        # Since join() returns in caller thread
        # we re-raise the caught exception
        # if any was caught
        if self.excecption:
            raise self.excecption


class ImageProducer(PilapseThread, Configurable):
    ARGS_ADDED = False
    @classmethod
    def add_arguments_to_parser(cls, parser:argparse.ArgumentParser, argument_group_name:str='Images')->argparse.ArgumentParser:
        logging.debug(f'ImageProducer({cls}) add_arguments: ADDED: {ImageProducer.ARGS_ADDED}')
        if ImageProducer.ARGS_ADDED:
            return parser
        Configurable.add_arguments_to_parser(parser)
        images = parser.add_argument_group(argument_group_name, 'Parameters related to creating images')
        images.add_argument('--width', '-W', type=int, help='width of each image', default=640)
        images.add_argument('--height', '-H', type=int, help='height of each image', default=480)
        images.add_argument('--nframes', type=int,
                             help='Stop after creating this many images. (useful for testing setup)')
        ImageProducer.ARGS_ADDED = True
        return parser

    THROTTLE_DELAY = 0.1
    def __init__(self, name:str, shutdown_event:threading.Event, config:argparse.Namespace, **kwargs):
        super(ImageProducer, self).__init__(name, shutdown_event, config, **kwargs)
        self.process_config(config)
        logging.debug(f'ImageProducer init {self.name}')
        self.out_queue:Queue = kwargs.get('out_queue')
        if self.out_queue is None:
            raise Exception(f'Creating Producer thread {self.name} with no out queue')
        self.system:SystemResources = SystemResources()
        self.throttled = False
        self.nframes_count:int = 0

    def log_status(self):
        elapsed = self.now - self.start_time
        elapsed_str = str(elapsed).split('.')[0]
        # TODO: nframes is owned by ImageProducer
        FPS = self.nframes_count / elapsed.total_seconds()
        logging.info(f'{elapsed_str} frames: {self.nframes_count} FPS: {FPS:.2f}, Qout: {self.out_queue.qsize()}')

    def preproduce(self):
        logging.debug(f'ImageProducer preproduce')
        throttle, message = self.system.should_throttle_back()
        logging.debug(f'throttle: {throttle} {message}')
        if throttle == 0:
            if self.throttled:
                logging.info(f'Unthrottling: {message}')
            self.throttled = False
        if throttle == 1:
            if not self.throttled:
                logging.info(f'Throttling: {message}')
            self.throttled = True
        if throttle == 2:
            logging.error(f'NEED TO SHUTDOWN: {message}')
            self.signal_shutdown()
            return False
        if self.system.check_for_undercurrent():
            logging.error(f'Undercurrent detected. Shutting down')
            self.signal_shutdown()
            return False

        if self.config.nframes is not None and self.nframes_count >= self.config.nframes:
            logging.info(f'nframes ({self.nframes_count}) from config ({self.config.nframes}) exceeded. Stopping.')
            self.shutdown_event.set()
            return False

        return True

    def add_to_out_queue(self, image):
        if image is not None:
            self.nframes_count += 1
            logging.debug(f'ADDING IMAGE {self.nframes_count} TO QUEUE')
            self.out_queue.put(image)

    def do_work(self) -> None:
        self.start_work()
        shutdown_event = self.shutdown_event
        logging.info(f'do_work: ImageProducer: {self.name}')
        while True:
            if shutdown_event.is_set():
                logging.info('Shutdown event received')
                break
            self.now = datetime.now()
            if self.preproduce():
                image = self.produce_image()
                self.add_to_out_queue(image)
            self.log_status()
            if self.throttled:
                self.shutdown_event.wait(self.THROTTLE_DELAY)

    def produce_image(self) -> str:
        raise Exception('Base class cannot produce images')

class DirectoryProducer(ImageProducer):
    ARGS_ADDED = False
    @classmethod
    def add_arguments_to_parser(cls, parser:argparse.ArgumentParser, argument_group_name:str='Image Input')->argparse.ArgumentParser:
        logging.debug(f'DirectoryProducer({cls}) add_arguments: ADDED: {DirectoryProducer.ARGS_ADDED}')
        if DirectoryProducer.ARGS_ADDED:
            return parser
        ImageProducer.add_arguments_to_parser(parser)
        directory = parser.add_argument_group(argument_group_name, 'Parameters related to loading image files')

        directory.add_argument('--source-dir', type=str,
                           help='If source-dir is set, images will be loaded from files in a directory instead')

        return parser

    class Handler(watchdog.events.PatternMatchingEventHandler):
        def __init__(self, patterns:list, file_event_queue:queue.Queue):
            # Set the patterns for PatternMatchingEventHandler
            watchdog.events.PatternMatchingEventHandler.__init__(self, patterns=patterns,
                                                                 ignore_directories=True,
                                                                 case_sensitive=True)
            self.out_queue:Queue = file_event_queue

        def on_created(self, event):
            # logging.info(f"Watchdog received created event - {event.src_path}")
            self.out_queue.put(event.src_path)

    def __init__(self, ext:str, shutdown_event:threading.Event, config:argparse.Namespace, **kwargs):
        super(DirectoryProducer, self).__init__('DirectoryProducer', shutdown_event, config, **kwargs)
        logging.info(f'DirectoryProducer({config.source_dir}, {ext}, {kwargs.get("out_queue")}, {shutdown_event})')
        self.dirpath:str = config.source_dir
        self.extension:str = ext
        self.new_file_queue:Queue = Queue()
        self.handler:DirectoryProducer.Handler = DirectoryProducer.Handler([f'*.{ext}'], self.new_file_queue)
        self.directory_observer = watchdog.observers.Observer()
        self.directory_observer.schedule(self.handler, path=self.dirpath, recursive=False)

    def do_work(self) -> None:
        self.start_work()
        if self.shutdown_event.is_set():
            logging.info('Shutdown event received at beginning of do_work')
            return
        #  Load the exiting files, start the observer
        logging.info(f'DirectoryProducer: do_work: {self.name}')
        self.directory_observer.setName('DirectoryObserver')
        self.directory_observer.start()
        self.existing_files = glob(f'{self.dirpath}/*.{self.extension}')
        self.existing_files.sort()
        for file in self.existing_files:
            if self.shutdown_event.is_set():
                logging.info('Shutdown event received while processing existing files')
                break
            logging.debug(f'Existing File: {file}')
            fimage = FileImage(file)
            if fimage.image is not None:
                self.out_queue.put(fimage)
        look_for_dups = True
        while True:
            if self.shutdown_event.is_set():
                logging.info('Shutdown event received while processing new files')
                break
            if self.throttled:
                self.shutdown_event.wait(self.THROTTLE_DELAY)
                if self.shutdown_event.is_set():
                    continue
            self.now = datetime.now()
            if not self.new_file_queue.empty():
                # get the new image, make sure we don't have it already, put it in the outgoing queue
                image = FileImage(self.new_file_queue.get())
                if image.image is None:
                    continue
                if look_for_dups:
                    if not image in self.existing_files:
                        self.out_queue.put(image, block=True)
                        logging.debug(f'First New File: {image.filename}')
                        # if this file isn't in the existing files, we can deallocate that list (we are past the end)
                        self.existing_files = []
                        look_for_dups = False
                    else:
                        # logging.info(f'Dup File: {image}')
                        pass
                else:
                    self.out_queue.put(image, block=True)
                    logging.debug(f'New File: {image.filename}')


class ImageConsumer(PilapseThread):
    ARGS_ADDED = False
    # TODO: should base classes implement "add args to group" function?
    @classmethod
    def add_arguments_to_parser(cls, parser:argparse.ArgumentParser, argument_group_name:str='Image Output Settings')->argparse.ArgumentParser:
        if ImageConsumer.ARGS_ADDED:
            return parser
        images = parser.add_argument_group(argument_group_name, 'Parameters related to outputting images')
        ImageConsumer.add_arguments_to_group(images)

        ImageConsumer.ARGS_ADDED = True
        return parser

    @classmethod
    def add_arguments_to_group(cls, group:argparse.ArgumentParser):
        group.add_argument('--outdir', type=str,
                            help='directory where frame files will be written.',
                            default='./%Y%m%d')
    def __init__(self, name:str, shutdown_event:threading.Event, config:argparse.Namespace, **kwargs):
        super(ImageConsumer, self).__init__(name, shutdown_event, config)
        logging.debug(f'ImageConsumer init {self.name}')
        self.in_queue:Queue = kwargs.get('in_queue')
        if self.in_queue is None:
           raise Exception(f'Creating Consumer thread {self.name} with no in queue')
        self._shutdown_event:threading.Event = shutdown_event
        # self.nframes:int = 0
        self.keepers:int = 0
        self.start_time:datetime = datetime.now()
        self.now:datetime = self.start_time
        self.paused:bool = False

        self.outdir:str = self.config.outdir
        if '%' in self.outdir:
            self.outdir = datetime.strftime(datetime.now(), self.config.outdir)
        os.makedirs(self.outdir, exist_ok=True)

        self.current_time = self.now

        self.force_consume = False

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
            thermal_temp_file = '/sys/class/thermal/thermal_zone0/temp'
            temp = '-'
            t = '--'
            if os.path.exists(thermal_temp_file):
                with open(thermal_temp_file) as f:
                    temp = int(f.read().strip()) / 1000
                p = subprocess.run(['vcgencmd', 'measure_temp'], capture_output=True)
                t = p.stdout.decode()
                r = r'^temp=([.0-9]+)'
                m = re.match(r, t)
                t = m.group(1) if m is not None else ''
            d = shutil.disk_usage(self.outdir)
            disk_usage = d.used / d.total * 100.0
            # NOTE GPU temp should stay below 85
            logging.info(f'{os.uname()[1]}: CPU {psutil.cpu_percent()}%, mem {psutil.virtual_memory().percent}% disk: {disk_usage:.1f}% TEMP CPU: {temp:.1f}C GPU: {t}C')
            logging.info(f'saved: {self.keepers} Paused: {self.paused} Q: {self.in_queue.qsize()}')
            self.report_time = self.report_time + self.report_wait


    def check_for_shutdown(self):
        if self._shutdown_event.is_set():
            logging.warning(f'shutdown event is set')
            if self.in_queue.empty():
                logging.info('Queue is empty. Shutting down')
                return True
            logging.warning(f'Trying to shutdown, but queue not empty: {self.in_queue.qsize()}')
            self.force_consume = True
        return False

    def check_in_queue(self):
        if not self.in_queue.empty():
            logging.debug(f'In-Queue not empty {self}')
            if self.preconsume() or self.force_consume:
                image = self.in_queue.get()
                self.consume_image(image)
            else:
                logging.debug(f'preconsume returned false.')
        else:
            self.shutdown_event.wait(0.001)

    def do_work(self) -> None:
        self.start_work()
        logging.info(f'Starting ImageConsumer (do_work) ({self.start_time.strftime("%Y/%m/%d %H:%M:%S")})')
        logging.debug(f'Config: {self.config}')
        self.paused = False if self.config.run_from is None else True
        force_consume = False
        while True:
            # DUPLICATE IN ImageWriter
            # Have we received shutdown event?
            if self.check_for_shutdown():
                break
            self.now = datetime.now()
            self.set_outdir()

            self.log_status()
            self.check_in_queue()

    def consume_image(self, image):
        logging.error(f'Base class Consuming {image.filename} ({self}')

class ImageWriter(ImageConsumer):
    ARGS_ADDED = False
    @classmethod
    def add_arguments_to_parser(cls, parser:argparse.ArgumentParser, argument_group_name:str='Image File Settings')->argparse.ArgumentParser:
        if ImageWriter.ARGS_ADDED:
            return parser
        images = parser.add_argument_group(argument_group_name, 'Parameters related to image files')
        super().add_arguments_to_group(images)
        ImageWriter.add_arguments_to_group(images)
        ImageWriter.ARGS_ADDED = True
        return parser

    @classmethod
    def add_arguments_to_group(cls, group:argparse.ArgumentParser):
        group.add_argument('--prefix', type=str, default='motion',
                            help='Prefix frame filenames with this string')
        group.add_argument('--show-camera-settings', action='store_true',
                           help='If the image is a CameraImage and the image has camera settings, '
                                'annotate the image with those settings')

    def __init__(self, shutdown_event:threading.Event, config:argparse.Namespace, **kwargs):
        super(ImageWriter, self).__init__('ImageWriter', shutdown_event, config, **kwargs)
        logging.info(f'ImageWriter init {self.name} ({self})')
        logging.info(f'LABEL_RGB: {self.config.label_rgb}')
        if self.config.label_rgb is not None:
            (R,G,B) = self.config.label_rgb.split(',')
            self.config.label_rgb = BGR(int(R), int(G), int(B))
            logging.info(f'FIXED label rgb: {self.config.label_rgb}')

    def do_work(self) -> None:
        self.start_work()
        logging.info(f'Starting Image Writer (do_work for {self.name}) ({self.start_time.strftime("%Y/%m/%d %H:%M:%S")})')
        while True:
            # DUPLICATE IN ImageWriter
            if self.check_for_shutdown():
                break
            self.now = datetime.now()
            self.set_outdir()

            self.log_status()
            self.check_in_queue()

    def consume_image(self, image):
        path = image.filepath
        logging.debug(f'Input image type: {type(image)}  ({self})')
        if self.config.show_name or self.config.show_camera_settings:
            pilapse.annotate_frame(image.image,
                                   image.timestamp_human,
                                   self.config,
                                   position='ul')
        if isinstance(image, CameraImage):
            path = os.path.join(self.outdir, image.filename)
            if self.config.show_camera_settings is not None and image.camera_settings is not None:
                settings = image.camera_settings
                settings_string = f'shutter speed: {settings["shutter-speed"]:.4f} '
                if settings['lux'] is not None:
                    settings_string += f' lux: {settings["lux"]:.4f} '
                settings_string += f'iso: {settings["iso"]}\n'
                settings_string += \
                    f'exp mode: {settings["exposure-mode"]} met mode: {settings["meter-mode"]} ' \
                    f'awb mode: {settings["awb-mode"]}\n'
                settings_string += \
                    f'gains: digital: {settings["digital-gain"]:.4f} analog: {settings["analog-gain"]:.4f} ' \
                    f'awb: ({settings["awb-gains"][0]:.4f},{settings["awb-gains"][1]:.4f})'
                pilapse.annotate_frame(image.image,
                                       settings_string,
                                       self.config,
                                       position='ll', text_size=0.5)
        logging.debug(f'## writing {path}')
        cv2.imwrite(path, image.image)

class ImagePipeline(ImageProducer, ImageConsumer):
    def __init__(self, name:str, shutdown_event:threading.Event, config:argparse.Namespace,
                 **kwargs):
        super(ImagePipeline, self).__init__(name, shutdown_event, config, **kwargs)

    def log_status(self):
        if self.now > self.report_time:
            elapsed = self.now - self.start_time
            elapsed_str = str(elapsed).split('.')[0]
            FPS = self.nframes_count / elapsed.total_seconds()

            logging.info(f'{elapsed_str} frames: {self.nframes_count} FPS: {FPS:.2f} Qin: {self.in_queue.qsize()} Qout: {self.out_queue.qsize()}')
            self.report_time = self.report_time + self.report_wait

    def do_work(self) -> None:
            self.start_work()
            logging.info(f'Starting Image Pipeline (do_work for {self.name}) ({self.start_time.strftime("%Y/%m/%d %H:%M:%S")})')
            while True:
                if self.check_for_shutdown():
                    break
                self.now = datetime.now()
                self.set_outdir()
                self.log_status()
                self.check_in_queue()


class MotionPipeline(ImagePipeline):
    def __init__(self, shutdown_event:threading.Event, config:argparse.Namespace, **kwargs):
        super(MotionPipeline, self).__init__('MotionPipeline', shutdown_event, config, **kwargs)
        logging.debug(f'MotionPipeline init {self.name}')
        self.current_image:Image = None
        self.previous_image:Image = None
        self.previous_image_name:str = None
        self.count:int = 0
        self.paused:bool = False
        self.motion_end:datetime = None
        self.motion_wait:timedelta = timedelta(seconds=3)

        if self.config.label_rgb is not None:
            (R,G,B) = self.config.label_rgb.split(',')
            self.config.label_rgb = BGR(int(R), int(G), int(B))
            logging.info(f'MOTION: Fixed label rgb: {self.config.label_rgb}')

    def preconsume(self) -> bool:
        # If nframes is set, have we exceeded it?
        # ImageProducer does this
        if self.config.nframes and self.nframes_count > self.config.nframes:
            logging.info(f'Reached limit ({self.config.nframes} frames). Stopping.')
            self.signal_shutdown()
            return False
        return True

    def adjust_config(self, w, h) -> None:
        self.config.width = w
        self.config.height = h
        self.config.bottom = int(self.config.bottom * h)
        self.config.top = int(self.config.top * h)
        self.config.left = int(self.config.left * w)
        self.config.right = int(self.config.right * w)

    def consume_image(self, image:Image) -> None:
        self.previous_image = self.current_image
        self.current_image = image

        logging.debug(f'Consuming image: {image.filename}, Q in: {self.in_queue.qsize()}')
        fname_base = self.current_image.base_filename
        new_name = f'{fname_base}_90.{self.current_image.type}' if self.config.save_diffs else f'{fname_base}.{self.current_image.type}'
        new_name_motion = f'{fname_base}_90M.{self.current_image.type}'

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

                path = os.path.join(self.outdir, new_name_motion)
                path = path.replace('90M', '90MT')
                logging.debug(f'Writing Test Image: {path}')
                if isinstance(image, CameraImage):
                    test_image = CameraImage(copy, prefix=self.config.prefix, suffix='10MT', timestamp=image.timestamp)
                    test_image.copy_camera_settings(image.camera_settings)
                else:
                    test_image = FileImage(path, image=copy)
                self.add_to_out_queue(test_image)
                # cv2.imwrite(path, copy)
        elif self.previous_image is not None and self.current_image is not None:
                img_out, motion_detected = self.compare_images()
                if motion_detected:
                    new_name = new_name_motion
                    logging.info(f'Motion Detected: {new_name}')
                    if self.motion_end is None:
                        logging.debug(f'New motion detected, saving previous frame for context')
                        copy = self.previous_image.image.copy()

                        path = os.path.join(self.outdir, self.previous_image_name)
                        if isinstance(image, CameraImage):
                            image_out = CameraImage(copy, prefix=self.config.prefix, suffix='70p', timestamp=image.timestamp)
                            image_out.copy_camera_settings(image.camera_settings)
                        else:
                            image_out = FileImage(path, image=copy)
                        self.add_to_out_queue(image_out)
                    self.motion_end = datetime.now() + self.motion_wait
                elif self.motion_end is not None:
                        if datetime.now() <= self.motion_end:
                            logging.debug(f'No new motion detected but still waiting. end time: {self.motion_end}')

                            copy = self.current_image.image.copy()

                            path = os.path.join(self.outdir, new_name_motion.replace('80M', '90m'))
                            if isinstance(image, CameraImage):
                                image_out = CameraImage(copy, prefix=self.config.prefix, suffix='90m', timestamp=image.timestamp)
                                image_out.copy_camera_settings(image.camera_settings)
                            else:
                                image_out = FileImage(path, image=copy)
                            self.add_to_out_queue(image_out)
                        else:
                            self.motion_end = None

                if img_out is not None:
                    logging.debug(f'{new_name}')
                    self.keepers += 1
                    path = os.path.join(self.outdir, new_name)
                    logging.debug(f'Writing Motion frame: {path}')
                    if isinstance(image, CameraImage):
                        image_out = CameraImage(img_out, prefix=self.config.prefix, suffix='80M', timestamp=image.timestamp)
                        image_out.copy_camera_settings(image.camera_settings)
                    else:
                        image_out = FileImage(path, image=img_out)
                    self.add_to_out_queue(image_out)

                elif self.config.all_frames:
                    path = os.path.join(self.outdir, new_name)
                    logging.debug(f'Writing all frames: {path}')
                    self.add_to_out_queue(self.current_image)
                    # cv2.imwrite(path, self.current_image.image)

        self.previous_image_name = new_name_motion.replace('_90M', '_90p')

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
                self.add_to_out_queue(FileImage(path, image=new))
                # cv2.imwrite(path, new)


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
            self.add_to_out_queue(FileImage(path, image=diff2))
            # cv2.imwrite(path, diff2)

        #converting the difference into grascale
        gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        # 02 - gray
        if config.save_diffs:
            gray2 = gray.copy()
            gray2 = imutils.resize(gray2, config.height)
            gray_name = f'{fname_base}_02G.png'
            path = os.path.join(self.outdir, gray_name)
            logging.debug(f'Saving: {path}')
            self.add_to_out_queue(FileImage(path, image=gray2))
            # cv2.imwrite(path, gray2)

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
            self.add_to_out_queue(FileImage(path, image=dilated2))
            # cv2.imwrite(path, dilated2)

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
            self.add_to_out_queue(FileImage(path, image=thresh2))
            # cv2.imwrite(path, thresh2)

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
