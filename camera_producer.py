import argparse
import logging
import re
import subprocess
import threading

import pause

import threads
from camera import Camera
from pilapse import BGR
from threads import ImageProducer, CameraImage
from scheduling import Schedule
from config import Configurable

from datetime import datetime, timedelta
import time


class CameraProducer(ImageProducer):
    # TODO base class producer should be aware of
    #    - "pause" due to run_from / run_until
    #    - stop_at
    #    - nframes
    # or move that control into app?
    ARGS_ADDED = False
    @classmethod
    def add_arguments_to_parser(cls, parser:argparse.ArgumentParser, argument_group_name:str= 'Camera Settings')->argparse.ArgumentParser:
        logging.debug(f'Adding CameraProducer({cls}) args (ADDED: {CameraProducer.ARGS_ADDED})')
        if CameraProducer.ARGS_ADDED:
            return parser
        # CameraProducer is an ImageProducer. Call the base class
        threads.ImageProducer.add_arguments_to_parser(parser)

        camera = parser.add_argument_group(argument_group_name, 'Parameters related to the camera')
        camera.add_argument('--zoom', type=float, help='Zoom factor. Must be greater than 1.0', default=1.0)
        camera.add_argument('--framerate', type=float, default=None,
                           help='Framerate of the camera. '
                                'Int value. Units is seconds. EX. Setting framerate to "3" will take a frame every'
                                '3 seconds. Defaults to 0 which means "as fast as you can" ')

        camera.add_argument('--exposure-mode', type=str, default='auto',
                            help='Exposure mode. See '
                                 'https://picamera.readthedocs.io/en/release-1.13/api_camera.html#picamera.PiCamera.exposure_mode')
        camera.add_argument('--meter-mode', type=str, default='average',
                            help='See '
                                 'https://picamera.readthedocs.io/en/release-1.13/api_camera.html#picamera.PiCamera.meter_mode')
        camera.add_argument('--show-name', action='store_true',
                           help='Write a timestamp on each frame')
        camera.add_argument('--label-rgb', type=str,
                           help='Set the color of the timestamp on each frame. '
                                'FORMAT: comma separated integers between 0 and 255, no spaces EX: "R,G,B" ')

        CameraProducer.ARGS_ADDED = True
        # CameraProducer owns a Schedule instance
        Schedule.add_arguments_to_parser(parser, 'Scheduling')
        return parser

    def process_config(self, config):
        logging.debug(f'CONFIG: {config}')
        super().process_config(config)

        if config.zoom < 1.0:
            msg = f'Zoom must be 1.0 or greater. (set to: {config.zoom})'
            raise Exception(msg)

        if config.label_rgb is not None:
            (R,G,B) = config.label_rgb.split(',')
            self.label_rgb = BGR(int(R), int(G), int(B))

    def __init__(self,
                 shutdown_event:threading.Event, config:argparse.Namespace,
                 **kwargs):
        super(CameraProducer, self).__init__('CameraProducer', shutdown_event, config, **kwargs)
        logging.debug(f'CameraProducer init {self.name}')
        self.process_config(config)

        self.width:int = config.width
        self.height:int = config.height
        self.prefix:str = config.prefix
        ar = config.width/config.height
        ar_16_9 = 16/9
        ar_4_3 = 4/3
        d1 = abs(ar-ar_16_9)
        d2 = abs(ar-ar_4_3)
        ar = '4:3' if d1 > d2 else '16:9'
        self.camera:Camera = Camera(config.width, config.height,
                                    zoom=config.zoom,
                                    exposure_mode=config.exposure_mode,
                                    meter_mode=config.meter_mode,
                                    aspect_ratio=ar, pause=10)
        if self.config.framerate:
            self.config.framerate_delta = timedelta(seconds=config.framerate)

        self.nextframe_time = self.now
        self.schedule = Schedule(self.config)

        time.sleep(10) # let the camera self calibrate

    def get_camera_model(self):
        return self.camera.model

    def log_status(self):
        # logging.info(f'LOG STATUS: now: {self.now}, report time: {self.report_time}')
        if self.now > self.report_time:
            elapsed = self.now - self.start_time
            with open('/sys/class/thermal/thermal_zone0/temp') as f:
                temp = int(f.read().strip()) / 1000
            p = subprocess.run(['vcgencmd', 'measure_temp'], capture_output=True)
            t = p.stdout.decode()
            r = r'^temp=([.0-9]+)'
            m = re.match(r, t)
            t = m.group(1) if m is not None else ''

            # logging.info(f'# {os.uname()[1]}: CPU {psutil.cpu_percent()}%, mem {psutil.virtual_memory().percent}%, TEMP CPU: {temp:.1f}C GPU: {t}C')
            logging.info(f'{self.system.model}')
            logging.info(f'Camera Model: {self.get_camera_model()}')
            super().log_status()
            logging.info(f'Qout: {self.out_queue.qsize()}, '
                         f'Paused: {"T" if self.schedule.paused else "F"}')
            logging.info(f'{self.system.status_string()}, throttling: {self.throttled}')
            self.report_time = self.report_time + self.report_wait

    def check_run_until(self):
        if self.schedule.paused:
            time.sleep(1)
            return False
        return True

    def check_stop_at(self):
        if self.schedule.stopped:
            logging.info(f'Shutting down due to "stop_at": {self.config.stop_at.strftime("%Y/%m/%d %H:%M:%S")}')
            self.shutdown_event.set()
            return False
        return True

    def preproduce(self):
        if not super().preproduce():
            return False

        self.schedule.update()

        if not self.check_run_until():
            logging.debug(f'Run Until Check Failed')
            return False

        if not self.check_stop_at():
            logging.info(f'Stop At Check Failed. Shutting down')
            self.shutdown_event.set()
            return False

        return True
    def produce_image(self) -> str:
        if not self.shutdown_event.is_set():
            if self.out_queue.full():
                logging.warning('Output Queue is full')
                time.sleep(0.001)
                return
            img = CameraImage(self.camera.capture(), prefix=self.prefix, type='png')
            logging.debug(f'captured {img.base_filename}')
            self.add_to_out_queue(img)

            if self.config.framerate:
                logging.debug(f'now: {self.now}, delta: {self.config.framerate_delta}')
                self.nextframe_time = self.now + self.config.framerate_delta
                logging.debug(f'nextframe_time: {self.nextframe_time}')
                if self.config.debug:
                    logging.info(f'Pausing until {self.nextframe_time} (framerate:{self.config.framerate})')
                pause.until(self.nextframe_time)
