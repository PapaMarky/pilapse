#!/usr/bin/env python3

'''
Specify camera settings (iso, shutter) for:
first_light, dawn, sunrise,
solar_noon,
sunset, dusk, last_light

and extrapolate the camara setting values based on current time, resetting the camera when they change.

Based on
https://learn.adafruit.com/raspberry-pi-hq-camera-low-light-long-exposure-photography/python-code

'''

import argparse
import json
import os
import signal
import sys
import logging
import threading

import pause
from picamera import PiCamera
import time
from fractions import Fraction
import datetime

from pause_until import pause_until
from scheduling import Schedule
from suntime import Suntime

location=(37.335480, -121.893028)

def get_program_name():
    name = os.path.basename(sys.argv[0])
    s = name.split('.')
    if s[-1] == 'py':
        name = '.'.join(s[:-1])
    return name

logfile = os.environ.get('LOGFILE')
print(f'Logging to {logfile}')

logging.basicConfig(
    filename=logfile,
    level=logging.INFO,
    format='%(asctime)s|%(levelname)s|%(threadName)s|%(message)s'
)

class NightCam:
    def __init__(self, shutdown_event:threading.Event):
        logging.info('init NightCam')
        self._model = None
        self.start_time = datetime.datetime.now()
        self.shutdown_event = shutdown_event
        self.iso:int = 0
        self.shutter:int = 0
        self.nframes:int = 8
        self.parse_command_line()
        self.load_suntimes()
        self.schedule = Schedule(self.config)
        self.camera:PiCamera = None
        self.running:bool = False
        self.create_camera()


    def load_suntimes(self):
        self.suntimes = Suntime(location)

    def camera_model(self) -> str:
        if self._model:
            return self._model

        rev = self.camera.revision
        known = {
            'ov5647': 'V1',
            'imx219': 'V2'
        }
        if rev in known:
            rev = known[rev]


        self._model = rev
        return self._model

    # TODO: Use camera_producer model.
    def create_camera(self):
        logging.info('create PiCamera')
        self.camera = PiCamera(framerate_range=(1/10, 40),
                               resolution=(self.config.width,self.config.height),
                               sensor_mode=5
                               )
        logging.info(f'Model: {self.camera_model()}')
        self.camera.rotation = 180
        s = 1.0 / self.config.zoom
        p0 = 0.5 - s/2
        p1 = 0.5 + s/2
        self.camera.zoom = (p0, p0, p1, p1)
        try:
            self.camera.led = False
        except:
            logging.info('Failed to turn off LED. Oh well.')
        # self.camera.awb_mode = 'auto'
        self.camera.exposure_mode='nightpreview'

    def stop_running(self):
        logging.info(f'Camera: stop running')
        self.running = False

    def check_for_undercurrent(self):
        """
        Check to see if undercurrent condition has occured. Our goal is to shutdown safely before the battery dies.
        :return: True if an under current has happened, False if not.
        """
        # my goal is to shutdown the software safely before the battery dies. 16 is the one I should check
        bits = {
            0: 'under-voltage',
            1: 'arm frequency capped',
            2: 'currently throttled',
            16: 'under-voltage has occurred',
            17: 'arm frequency capped has occurred',
            18: 'throttling has occurred'
        }

        with open('/sys/devices/platform/soc/soc:firmware/get_throttled') as f:
            val = f.read()
            n = int(val, 16)
            if n & 16**2:
                return True
        return False

    def run(self):
        logging.info(f'running camera...')
        self.running = True
        frame_time = datetime.timedelta(seconds=self.config.sleep)
        quiting_time = datetime.datetime.now() + datetime.timedelta(days=1)
        # shutdown at 7 am tomorrow
        quiting_time.replace(hour=7, minute=0, second=0, microsecond=0)
        while self.running:
            if self.shutdown_event.is_set():
                self.stop_running()
                break
            if self.check_for_undercurrent():
                logging.error('Undercurrent detected. Shutting down')
                self.stop_running()
                break
            start_time = datetime.datetime.now()
            if start_time >= quiting_time:
                self.stop_running()
                break
            if start_time.day != self.start_time.day:
                self.load_suntimes()
                self.start_time = start_time

            next_frame_time = start_time + frame_time
            self.update_camera()
            self.take_picture()
            if self.single_shot:
                self.nframes = self.nframes - 1
                logging.info(f'NFRAMES: {self.nframes}')
                if self.nframes <= 0:
                    logging.info(f'Single shot, exiting...')
                    break
                else:
                    logging.info(f'** {self.nframes} more frames to go...')

            if self.running:
                logging.info(f'Sleeping until {next_frame_time}')
                # TODO: rewrite "pause" that uses an Event.wait
                pause_until(next_frame_time, self.shutdown_event)
        self.destroy_camera()

    def destroy_camera(self):
        if self.camera is not None:
            self.camera.close()
            self.camera = None

    def take_picture(self):
        cur_time = datetime.datetime.now()

        dirpath = self.config.outdir
        pathtemplate = f'{dirpath}/{self.config.filename}'
        # print(f'path template: "{pathtemplate}"')
        part_of_day = self.suntimes.get_part_of_day(cur_time)
        pathtemplate = pathtemplate.replace('%ISO%', f'{self.iso}')
        pathtemplate = pathtemplate.replace('%SHUTTER%', f'{self.shutter}')
        pathtemplate = pathtemplate.replace('%TIMEOFDAY%', part_of_day)
        outfile = cur_time.strftime(f'{pathtemplate}.{self.config.outtype}')
        # %TIMEOFDAY%
        # %TIMEOFDAY%
        if not os.path.exists(os.path.dirname(outfile)):
            print(f'- create dir: {os.path.dirname(outfile)}')
            os.makedirs(os.path.dirname(outfile))

        logging.info(f'Taking picture... ({outfile})')
        self.camera.capture(outfile, use_video_port=True)

        logging.info(f'Done. (elapsed: {datetime.datetime.now() - cur_time})')
        logging.info(f'AWB MODE: {self.camera.awb_mode} BRIGHTNESS: {self.camera.brightness} '
                     f'CONTRAST: {self.camera.contrast}')
        logging.info(f'analog gain: {self.camera.analog_gain}, awb gains: {self.camera.awb_gains}, '
                     f'digital gain: {self.camera.digital_gain}')
        logging.info(f'drc_strength: {self.camera.drc_strength}, exposure mode: {self.camera.exposure_mode} '
                     f'exposure compensation: {self.camera.exposure_compensation}')
        logging.info(f'exposure_speed: {self.camera.exposure_speed}, framerate_range: {self.camera.framerate_range}, '
                     f'framerate: {self.camera.framerate}')
        logging.info(f'meter_mode: {self.camera.meter_mode}, sensor_mode: {self.camera.sensor_mode}')

    def update_camera(self):
        logging.info(f'Updating Camera settings...')
        if self.camera is None:
            self.create_camera()

        if self.camera is not None:
            # shutter speed is microseconds (seconds * 1,000,000)
            # framerate will limit shutter speed.
            iso, shutter = self.calculate_camera_settings()
            # TODO: include framerate in the "has it changed" calculations
            # calculate framerate from shutter so they match
            if (self.single_shot and (self.iso != iso or self.shutter != shutter) ) or abs(self.iso - iso) > 10 or abs(self.shutter - shutter) > 10000:
                # TODO: should I turn exposure mode on before doing these things?
                logging.info(f' - Camera settings changed: iso: {iso}, shutter speed: {shutter}, framerate: {self.camera.framerate}')
                if self.config.meter_mode != '':
                    logging.info(f'   meter mode: {self.config.meter_mode}')
                    self.camera.meter_mode = self.config.meter_mode
                self.iso = iso
                self.shutter = shutter
                # self.framerate = framerate

                self.camera.iso = self.iso
                self.camera.shutter_speed = self.shutter
                # self.camera.shutter_speed = 0
                # self.camera.framerate = self.framerate
                # we set the framerate range

                logging.info(f'Sleep {self.config.sleep1} seconds to let camera calm itself')
                self.shutdown_event.wait(self.config.sleep1)
                self.camera.exposure_mode = 'off'
            else:
                logging.info(f'- Camera settings unchanged.')

    def calculate_camera_settings(self):
        if self.single_shot:
            return (self.config.iso, self.config.shutter, self.config.framerate)
        else:
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

    def parse_command_line(self):
        parser = argparse.ArgumentParser('Test Low Light long exposure')

        parser.add_argument('--shutter', type=int,
                            help='shutter speed in microseconds. '
                                 'Max 6000000 (6 seconds) default: 1750000',
                            default=1750000)
        parser.add_argument('--iso', type=int, help='ISO setting', default=800)
        '''When set, the property adjusts the sensitivity of the camera (by adjusting the analog_gain and digital_gain). 
        Valid values are between 0 (auto) and 1600. The actual value used when iso is explicitly set will be one of 
        the following values (whichever is closest): 100, 200, 320, 400, 500, 640, 800.
        '''
        parser.add_argument('--width', type=int, help='width of created images', default=1920)
        parser.add_argument('--height', type=int, help='height of created images', default=1080)
        parser.add_argument('--zoom', type=float, help='Zoom factor. Must be greater than 1.0', default=1.0)
        parser.add_argument('--sleep', type=float, help='Number of seconds to sleep between pictures', default=30.0)
        parser.add_argument('--settings', type=str,
                            help='path to json file with camera settings for each "time". '
                                 'Used as keyframes to calculate current values')
        parser.add_argument('--outdir', type=str, default='/home/pi/data/lowlight',
                            help='Path to directory where images will be stored')
        parser.add_argument('--filename', type=str, default='%Y%m%d%H%M%S_%ISO%_%SHUTTER%',
                            help='Pattern to use for filename. TODO: Document better')
        parser.add_argument('--outtype', type=str, default='jpg',
                            help='Type of image format to use ("png", "jpg", etc)')
        parser.add_argument('--logfile', type=str, default=f'{get_program_name()}.log',
                            help='Specify the name of the file to log output to.')
        parser.add_argument('--nframes', type=int, default=1,
                            help='Limit number of frames (for testing)')
        parser.add_argument('--sleep1', type=float, default=30,
                            help='set time to allow sensor to stabalize')
        parser.add_argument('--framerate', type=float, default=0.166667,
                            help='force the framerate')
        parser.add_argument('--meter-mode', type=str, default='',
                            help='ADVANCED. Set the meter mode.')
        Schedule.add_arguments_to_parser(parser)
        self.config = parser.parse_args()
        if self.config.logfile == 'stdout':
            self.config.logfile = None

        logging.info(f'    ISO: {self.config.iso}')
        logging.info(f'Shutter: {self.config.shutter} ({self.config.shutter/1000000:.4f} seconds)')
        logging.info(f'   Zoom: {self.config.zoom}')
        logging.info(f'  Sleep: {self.config.sleep}')

        logging.info(f'NFRAMES: {self.nframes} (default)')
        self.nframes = self.config.nframes
        logging.info(f'NFRAMES: {self.nframes}')

        if not self.single_shot:
            if not os.path.exists(self.config.settings):
                logging.info(f'Camera settings file not found ({self.config.settings})')

            with open(self.config.settings) as config_file:
                self.config.camera_settings = json.loads(config_file.read())

            logging.info(f'CONFIG: {self.config}')

    @property
    def single_shot(self):
        return self.config.settings is None

if __name__ == '__main__':
    shutdown_event = threading.Event()

    print(f'Create the camera...')
    night_camera = NightCam(shutdown_event)

    print(f'Setup signal handling...')


    def exit_gracefully(signum, frame):
        logging.info(f'SHUTTING {get_program_name()} DOWN due to {signal.Signals(signum).name}')
        shutdown_event.set()
        night_camera.stop_running()

    signal.signal(signal.SIGINT, exit_gracefully)
    signal.signal(signal.SIGTERM, exit_gracefully)

    print(f'Run the Camera...')
    print(f'NFRAMES: {night_camera.nframes}')
    night_camera.run()