import argparse
import json
import logging
import os
import queue
import re
import subprocess
import threading

from system_resources import SystemResources

import pilapse
import threads
from camera import Camera
from pause_until import pause_until
from pilapse import BGR
from threads import ImageProducer, CameraImage
from scheduling import Schedule
from light_meter import LightMeter
from suntime import Suntime

from datetime import datetime, timedelta


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

    # lux, shutterspeed table (iso = 100)
    LUX_SHUTTER_TABLE_100x = [
        (0.1152, 10),
        (0.1728, 5),
        (1, 1),
        (5, 0.1),
        (20, 0.05),
        (50, 0.0959),
        (224, 0.033),
        (400, 0.016),
        (474, 0.012),
        (594, 0.0094),
        (982, 0.005),
        (1200, 0.004),
        (1320, 0.0035),
        (1692, 0.0019),
        (1983, 0.00127),
        (2500, 0.00106),
        (3252, 0.00099)
    ]
    LUX_SHUTTER_TABLE_100 = [
        (0.1152, 10),
        (0.1728, 5),
        (1, 1),
        (10, 0.097),
        (50, 0.0347),
        (224, 0.022),
        (400, 0.016),
        (474, 0.012),
        (575, 0.0024),
        #(982, 0.005),
        #(1200, 0.003),
        (1320, 0.002),
        (1692, 0.0012),
        (1983, 0.001),
        (2500, 0.0010),
        (3252, 0.00099)
    ]

    @classmethod
    def shutter_speed_from_lux(cls, lux):
        for i in range(len(cls.LUX_SHUTTER_TABLE_100)):
            (l1, s1) = cls.LUX_SHUTTER_TABLE_100[i]
            if l1 >= lux:
                if i == 0:
                    return s1
                l0, s0 = cls.LUX_SHUTTER_TABLE_100[i-1]
                p = (lux - l0) / (l1 - l0)
                return s0 + p * (s1 - s0)
        return s1

    @classmethod
    def add_arguments_to_parser(cls,
                                parser:argparse.ArgumentParser,
                                argument_group_name:str= 'Camera Settings')->argparse.ArgumentParser:
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
        camera.add_argument('--awb-mode', type=str, default='auto', help='Set awb_mode on the camera')
        camera.add_argument('--iso', type=int, default=0,
                            help='Set the ISO of the camera to a fixed value. The actual value used when iso is '
                                 'explicitly set will be one of the following values (whichever is closest): '
                                 '100, 200, 320, 400, 500, 640, 800.')
        camera.add_argument('--show-name', action='store_true',
                           help='Write a timestamp on each frame')
        camera.add_argument('--label-rgb', type=str,
                           help='Set the color of the timestamp on each frame. '
                                'FORMAT: comma separated integers between 0 and 255, no spaces EX: "R,G,B" ')
        camera.add_argument('--camera-settings-log', default=None,
                           help='Create a log of each camera image written and the'
                                ' camera settings at the specified path.')
        camera.add_argument('--auto-cam', action='store_true',
                            help='Automatically update the camera shutter speed / iso based on time of day and / or '
                                 'light meter readings (if available)')

        camera.add_argument('--location', type=str,
                            help='latitude and longitude to use for getting the sunset/sunrise etc times. Two comma '
                                 'separated values')
        parser.add_argument('--suntime-settings', type=str,
                            help='path to json file with camera settings for each "suntime". '
                                 'Used as keyframes to calculate current values')

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
                 motion_event_queue:queue.Queue=None,
                 **kwargs):
        super(CameraProducer, self).__init__('CameraProducer', shutdown_event, config, **kwargs)
        logging.debug(f'CameraProducer init {self.name}')
        self.process_config(config)
        self.suntimes = None
        self.load_suntimes()

        self.width:int = config.width
        self.height:int = config.height
        self.prefix:str = config.prefix
        ar = config.width/config.height
        ar_16_9 = 16/9
        ar_4_3 = 4/3
        d1 = abs(ar-ar_16_9)
        d2 = abs(ar-ar_4_3)
        ar = '4:3' if d1 > d2 else '16:9'
        self.ar = ar
        self.camera:Camera = None
        self.create_camera()
        # we ignore exceptions from image capture. Use this value and MAX_CAPTURE_EXCEPTION
        # so that if the camera goes completely bonkers we shutdown cleanly instead of looping
        # out of control forever.
        self.capture_exception_count = 0
        self.capture_exception_count_total = 0

        if self.config.camera_settings_log is not None:
            if '%' in self.config.camera_settings_log:
                self.config.camera_settings_log = datetime.strftime(datetime.now(), self.config.camera_settings_log)
            logging.info(f'Logging camera settings to "{self.config.camera_settings_log}"')

        self.system = SystemResources()

        self.motion_event_queue = motion_event_queue
        self.current_video_clip = None
        logging.info(f'Video Enabled: {self.video_enabled}')
        self.video_temp_dir:str = os.path.expanduser(self.config.video_temp) if self.config.video else None
        if self.config.video:
            os.makedirs(self.video_temp_dir, exist_ok=True)

            if '%' in self.video_temp_dir:
                self.video_temp_dir = datetime.strftime(datetime.now(), self.config.outdir)
            os.makedirs(self.video_temp_dir, exist_ok=True)

    VIDEO_CLIP_DURATION = timedelta(seconds=15)
    @property
    def video_enabled(self):
        return self.config.video

    def create_camera(self):
        logging.info(f'Video Mode: {self.config.video}')
        self.camera:Camera = Camera(self.width, self.height,
                                    zoom=self.config.zoom,
                                    exposure_mode=self.config.exposure_mode,
                                    meter_mode=self.config.meter_mode,
                                    awb_mode=self.config.awb_mode,
                                    aspect_ratio=self.ar,
                                    iso=self.config.iso,
                                    video=self.config.video)

        self.light_meter = LightMeter()
        logging.info(f'Light meter available: {self.light_meter.available}')

        self.nextframe_time = self.now
        self.schedule = Schedule(self.config)
        if self.config.auto_cam:
            if self.config.suntime_settings:
                pass
            # need to calculate and set initial ISO / shutter speed
            iso, shutter_speed = self.calculate_camera_settings()
            logging.info(f'Before setting ISO to {iso}: analog gain: {self.camera.picamera.analog_gain}, '
                         f'digital gain: {self.camera.picamera.digital_gain}')
            self.camera.picamera.iso = iso
            self.camera.picamera.shutter_speed = shutter_speed

            # After setting iso, we need to wait for the digital / analog gain to settle down before we lock them into
            # place by setting exposure_mode to "off"
            pause = 30.0
            logging.info(f'Sleeping for {pause} seconds to let the sensor find itself')
            self.shutdown_event.wait(pause) # let the camera self calibrate
            if self.shutdown_event.is_set():
                logging.info('shutdown event received while waiting for camera')
            self.camera.exposure_mode = 'off'
            logging.info(f'After locking gains: analog gain: {self.camera.picamera.analog_gain}, '
                         f'digital gain: {self.camera.picamera.digital_gain}')
        else:
            self.camera.picamera.iso = self.config.iso
            self.shutdown_event.wait(2)

    def calculate_camera_settings(self):
        # zero means "let the camera decide" for both iso and shutter_speed
        iso = 0
        shutter_speed = 0
        if self.config.auto_cam:
            if self.light_meter.available:
                iso = 100
                shutter_speed = int(self.shutter_speed_from_lux(self.light_meter.lux) * 1000000)
                logging.info(f'setting camera from lux: shutter speed: {shutter_speed}')
                return iso, shutter_speed
            return self.calculate_camera_settings_from_time()
        else:
            iso = self.config.iso
        return iso, shutter_speed

    def start_video_clip(self):
        if self.video_enabled and not self.shutdown_event.is_set():
            if self.current_video_clip is not None:
                logging.error(f'Starting video, but current video is {self.current_video_clip}')

            timestamp_pattern:str = '%Y%m%d_%H%M%S.%f'
            timestamp = datetime.now()
            filename = f'{timestamp.strftime(timestamp_pattern)}_motion.h264'
            filepath = os.path.join(self.video_temp_dir, filename)
            self.camera.start_video_capture(filepath)
            logging.info(f'Starting video clip {filepath}')
            self.current_video_clip = {
                'start_time': timestamp,
                'end_time': timestamp + self.VIDEO_CLIP_DURATION,
                'file': filepath,
                'motion': False
            }
            logging.info(f'new video clip: {self.current_video_clip}')

    def end_video_clip(self):
        if self.video_enabled:
            if self.current_video_clip is None:
                logging.error(f'Ending video that has not started yet')
                return
            self.camera.stop_video_capture()
            if not self.current_video_clip['motion']:
                # delete the clip if it has no motion
                pass
            self.current_video_clip = None
            self.shutdown_event.set()

    def check_video_clip(self):
        if self.video_enabled:
            if self.current_video_clip is None:
                self.start_video_clip()
            # TODO this can raise an exception
            self.camera.check_video_capture()

            now = datetime.now()
            if self.current_video_clip['end_time'] <= now:
                logging.info(f'time to end clip passed: {self.current_video_clip["end_time"]}')
                logging.info(self.current_video_clip)
                self.end_video_clip()
                self.start_video_clip()



    def calculate_camera_settings_from_time(self):
        p0, p1, pct = self.suntimes.get_part_of_day_percent()
        iso0 = self.config.camera_settings[p0]['iso']
        shutter0 = self.config.camera_settings[p0]['shutter']

        iso1 = self.config.camera_settings[p1]['iso']
        shutter1 = self.config.camera_settings[p1]['shutter']

        iso = int(iso0) if iso0 == iso1 else int(iso0 + (iso1 - iso0) * pct)
        shutter = int(shutter0) if shutter0 == shutter1 else int(shutter0 + (shutter1 - shutter0) * pct)

        logging.info(f'      ISO: {iso0} - {iso1} ({pct:.4f}) {iso}')
        logging.info(f'  SHUTTER: {shutter0} - {shutter1} ({pct:.4f}) {shutter}')
        return (iso, shutter)

    def load_suntime_settings(self):
        self.config.camera_settings = None
        if self.config.auto_cam:
            if self.config.suntimes_settings:
                if not os.path.exists(self.config.suntimes_settings):
                    logging.info(f'Camera suntimes settings file not found ({self.config.suntimes_settings})')

                with open(self.config.settings) as config_file:
                    self.config.camera_settings = json.loads(config_file.read())

    def load_suntimes(self):
        if self.config.location:
            self.suntimes = Suntime(self.config.location)

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
        # check for motion_commands
        if self.video_enabled:
            if not self.motion_event_queue.empty():
                command = self.motion_event_queue.get()
                logging.info(f'Motion Command: {command}')
                if command['event'] == 'motion-detected':
                    logging.info(f'Motion detected event. Extending current video clip end time')
                    if self.current_video_clip is None:
                        logging.error(f'Got Motion Detected event but no current video')
                        return
                    self.current_video_clip['end_time'] = datetime.now() + self.VIDEO_CLIP_DURATION
            else:
                self.shutdown_event.wait(0.001)

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

        self.check_video_clip()

        if self.config.auto_cam:
            iso, shutter_speed = self.calculate_camera_settings()
            self.camera.picamera.iso = iso
            self.camera.picamera.shutter_speed = shutter_speed
            # do we need to pause?

        return True
    def produce_image(self) -> str:
        if self.shutdown_event.is_set():
            self.end_video_clip()
        else:
            if self.out_queue.full():
                logging.warning('Output Queue is full')
                self.shutdown_event.wait(0.001)
                return
            try:
                img = CameraImage(self.camera.capture(), prefix=self.prefix, type='jpg')
                lux = self.light_meter.lux if self.light_meter.available else None
                awb_gains = self.camera.picamera.awb_gains
                awb_gains = (float(awb_gains[0]), float(awb_gains[1]))
                img.set_camera_data(self.camera.picamera.exposure_speed/1000000,
                                    self.camera.picamera.ISO,
                                    self.aperture,
                                    self.camera.picamera.awb_mode,
                                    self.camera.picamera.meter_mode,
                                    self.camera.picamera.exposure_mode,
                                    float(self.camera.picamera.analog_gain),
                                    float(self.camera.picamera.digital_gain),
                                    awb_gains,
                                    lux)
                if self.config.camera_settings_log is not None:
                    with open(self.config.camera_settings_log, 'a') as logfile:
                        settings = img.camera_settings
                        logline = f'{img.timestamp_long},{settings["shutter-speed"]},{settings["iso"]},' \
                                  f'{settings["aperture"]},{settings["awb-mode"]},{settings["meter-mode"]},' \
                                  f'{settings["exposure-mode"]},{settings["analog-gain"]},{settings["digital-gain"]},' \
                                  f'{settings["lux"]},{self.camera.model},{pilapse.get_program_name()},' \
                                  f'{self.system.model},{self.system.hostname}\n'
                        logfile.write(logline)
                        logfile.flush()
                        logging.debug(f'SETTINGS: {logline}')

                logging.debug(f'captured {img.base_filename}')
                self.add_to_out_queue(img)
                # reset consecutive exception counter
                self.capture_exception_count = 0
            except Exception as e:
                logging.warning('Exception trying to capture image')
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

                logging.error(f'Exception capturing image: {e}')
                logging.info(f'Trying to recover from camera exception')
                # give the camera some time (arbitrary) to recover from the error
                self.camera = None
                self.create_camera()
                return

            if self.config.framerate:
                logging.debug(f'now: {self.now}, delta: {self.config.framerate_delta}')
                self.nextframe_time = self.now + self.config.framerate_delta
                logging.debug(f'nextframe_time: {self.nextframe_time}')
                if self.config.debug:
                    logging.info(f'Pausing until {self.nextframe_time} (framerate:{self.config.framerate})')
                pause_until(self.nextframe_time, self.shutdown_event)
