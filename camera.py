import logging
import time

from picamera.array import PiRGBArray
from picamera import PiCamera

class Camera():
    def __init__(self, config):
        self.config = config
        self.camera = PiCamera()
        logging.info('Setting up camera...')
        self.camera.resolution = (config.width, config.height)
        self.camera.rotation = 180
        self.camera.framerate = 80
        self.camera.exposure_mode = 'auto'
        self.camera.awb_mode = 'auto'
        # camera.zoom = (0.2, 0.3, 0.5, 0.5)
        time.sleep(2)
        logging.info(f'setup_camera completed: Camera Resolution: {self.camera.MAX_RESOLUTION}')

    def capture(self):
        logging.debug('Capturing image')
        rawCapture = PiRGBArray(self.camera)
        self.camera.capture(rawCapture, format="bgr")
        image = rawCapture.array
        return image

    def file_capture(self, filename):
        logging.debug(f'snap_picture({filename})')
        self.camera.capture(filename)

