import argparse
import datetime
import logging
import threading
import time

from picamera.array import PiRGBArray
from picamera import PiCamera


class Camera():
    def __init__(self,
                 width, height,
                 zoom=1.0,
                 rotation=180,
                 aspect_ratio='4:3',
                 exposure_mode='auto',
                 awb_mode='auto',
                 meter_mode='average',
                 iso=0,
                 video=False):
        self._model = None
        self._sensor_mode = None
        self._use_video_port = True

        if aspect_ratio == '4:3':
            self._sensor_mode = 4
        elif aspect_ratio == '16:9':
            self._sensor_mode = 5
        else:
            raise Exception(f'Aspect Ratio should be 4:3 or 16:9. Got {aspect_ratio}')

        # setting framerate_range throws an exception when start_recording is called:
        # picamera.exc.PiCameraValueError: framerate_delta cannot be used with framerate_range
        framerate_range = None if video else (1/10, 40)
        logging.info(f'Video mode: {video}')
        logging.info(f'framerate_range: {framerate_range}')
        self.camera = PiCamera(sensor_mode=self._sensor_mode,
                               framerate_range=framerate_range,
                               resolution=(width,height))
        modes = []
        for m in PiCamera.EXPOSURE_MODES:
            modes.append(m)
        logging.info(f'exposure modes: {modes}')
        modes = []
        for m in PiCamera.AWB_MODES:
            modes.append(m)
        logging.info(f'awb modes: {modes}')
        modes = []
        for m in PiCamera.METER_MODES:
            modes.append(m)
        logging.info(f'meter modes: {modes}')

        logging.info('Setting up camera...')
        s = 1.0 / zoom
        p0 = 0.5 - s/2
        p1 = 0.5 + s/2
        self.camera.zoom = (p0, p0, p1, p1)
        self.camera.rotation = rotation
        self.camera.exposure_mode = exposure_mode
        self.camera.awb_mode = awb_mode
        self.camera.meter_mode = meter_mode
        self.camera.iso = iso

        try:
            self.camera.led = False
        except:
            logging.info('Failed to turn off LED. Oh well.')

        logging.info(f'Camera {self.model}')
        logging.info(f' -   resolution: {width} x {height}')
        logging.info(f' - aspect ratio: {aspect_ratio}')
        logging.info(f' -         zoom: {zoom}')
        logging.info(f' -     rotation: {rotation}')
        logging.info(f'setup_camera completed: Camera Resolution: {self.camera.MAX_RESOLUTION}')
        logging.info(f' Model: {self.model}, Zoom: {self.zoom_str()}')

    @property
    def picamera(self):
        return self.camera

    def zoom_str(self) -> str:
        z = self.camera.zoom
        return f'({z[0]:.2f}, {z[1]:.2f}, {z[2]:.2f}, {z[3]:.2f})'

    @property
    def model(self) -> str:
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

    def start_video_capture(self, filename):
        self.picamera.start_recording(filename, format=None, splitter_port=1)
        logging.debug(f'Started recording video: {filename}')

    def stop_video_capture(self):
        self.picamera.stop_recording(splitter_port=1)

    def check_video_capture(self):
        """
        Give the video capture a chance to throw exceptions. Returns immediately or raises an exception
        :return:
        """
        self.picamera.wait_recording(splitter_port=1)

    def capture(self) -> PiRGBArray:
        logging.debug('Capturing image')
        rawCapture = PiRGBArray(self.camera)
        self.camera.capture(rawCapture, format="bgr", splitter_port=0)
        image = rawCapture.array
        return image

    def file_capture(self, filename):
        logging.debug(f'snap_picture({filename})')
        self.camera.capture(filename)

