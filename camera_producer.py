import argparse
import logging
import re
import subprocess
import threading

import pause

import threads
from camera import Camera
from pause_until import pause_until
from pilapse import BGR
from threads import ImageProducer, CameraImage
from scheduling import Schedule
from config import Configurable
from light_meter import LightMeter

from datetime import datetime, timedelta
import time


class CameraProducer(ImageProducer):
    # TODO base class producer should be aware of
    #    - "pause" due to run_from / run_until
    #    - stop_at
    #    - nframes
    # or move that control into app?
    ARGS_ADDED = False

    # Shutdown after MAX_CAPTURE_EXCEPTIONS consecutive exceptions
    MAX_CAPTURE_EXCEPTIONS = 10

    # Shutdown after MAX_CAPTURE_EXCEPTIONS_TOTAL total exceptions
    MAX_CAPTURE_EXCEPTIONS_TOTAL = 100
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
        camera.add_argument('--camera-settings-log', default=None,
                           help='Create a log of each camera image written and the'
                                ' camera settings at the specified path.')

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
                                    aspect_ratio=ar)
        if self.config.framerate:
            self.config.framerate_delta = timedelta(seconds=config.framerate)

        self.light_meter = LightMeter()

        self.nextframe_time = self.now
        self.schedule = Schedule(self.config)
        pause = 10.0
        logging.info(f'Sleeping for {pause} seconds to let the sensor find itself')
        shutdown_event.wait(pause) # let the camera self calibrate
        if shutdown_event.is_set():
            logging.info('shutdown event received while waiting for camera')

        # we ignore exceptions from image capture. Use this value and MAX_CAPTURE_EXCEPTION
        # so that if the camera goes completely bonkers we shutdown cleanly instead of looping
        # out of control forever.
        self.capture_exception_count = 0
        self.capture_exception_count_total = 0

        if self.config.camera_settings_log is not None:
            if '%' in self.config.camera_settings_log:
                self.config.camera_settings_log = datetime.strftime(datetime.now(), self.config.camera_settings_log)
            logging.info(f'Logging camera settings to "{self.config.camera_settings_log}"')

    def get_camera_model(self):
        return self.camera.model

    @property
    def aperture(self):
        # always the same. Probably
        return 2.8

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
            logging.info(f'{self.system.model}, Camera Model: {self.get_camera_model()}')
            super().log_status()
            logging.info(f'{self.system.status_string()}, throttling: {self.throttled}, Paused: {self.schedule.paused}')
            self.report_time = self.report_time + self.report_wait

    def check_run_until(self):
        if self.schedule.paused:
            self.shutdown_event.wait(1)
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
                self.shutdown_event.wait(0.001)
                return
            try:
                img = CameraImage(self.camera.capture(), prefix=self.prefix, type='jpg')
                lux = self.light_meter.lux if self.light_meter.available else None
                img.set_camera_data(self.camera.picamera.exposure_speed/1000000,
                                    self.camera.picamera.ISO,
                                    self.aperture,
                                    self.camera.picamera.awb_mode,
                                    self.camera.picamera.meter_mode,
                                    self.camera.picamera.exposure_mode,
                                    float(self.camera.picamera.analog_gain),
                                    float(self.camera.picamera.digital_gain),
                                    lux)
                if self.config.camera_settings_log is not None:
                    with open(self.config.camera_settings_log, 'a') as logfile:
                        settings = img.camera_settings
                        logline = f'{img.timestamp_long},{settings["shutter-speed"]},{settings["iso"]},' \
                                  f'{settings["aperture"]},{settings["awb-mode"]},{settings["meter-mode"]},' \
                                  f'{settings["exposure-mode"]},{settings["analog-gain"]},{settings["digital-gain"]},' \
                                  f'{settings["lux"]}\n'
                        logfile.write(logline)
                        logfile.flush()
                        logging.info(f'SETTINGS: {logline}')

                logging.debug(f'captured {img.base_filename}')
                self.add_to_out_queue(img)
                # reset consecutive exception counter
                self.capture_exception_count = 0
            except Exception as e:
                # if we get more than MAX_CAPTURE_EXCEPTIONS in a row, assume that something unrecoverable has gone
                # wrong, and shutdown
                self.capture_exception_count += 1
                if self.capture_exception_count > self.MAX_CAPTURE_EXCEPTIONS:
                    logging.error(f'Too many concecutive exceptions during image capture')
                    raise e

                # if we get more than MAX_CAPTURE_EXCEPTIONS_TOTAL, assume the camera has problems
                # and shutdown
                self.capture_exception_count_total += 1
                if self.capture_exception_count_total > self.MAX_CAPTURE_EXCEPTIONS_TOTAL:
                    logging.error(f'Too many total exceptions during image capture')
                    raise e

                logging.exception(f'Exception capturing image: {e}')
                # give the camera some time (arbitrary) to recover from the error
                self.shutdown_event.wait(0.1)
                return

            if self.config.framerate:
                logging.debug(f'now: {self.now}, delta: {self.config.framerate_delta}')
                self.nextframe_time = self.now + self.config.framerate_delta
                logging.debug(f'nextframe_time: {self.nextframe_time}')
                if self.config.debug:
                    logging.info(f'Pausing until {self.nextframe_time} (framerate:{self.config.framerate})')
                pause_until(self.nextframe_time, self.shutdown_event)
