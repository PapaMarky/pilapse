import logging
import time

from picamera.array import PiRGBArray
from picamera import PiCamera

class Camera():
    def __init__(self, width, height, zoom):
        #self.config = config
        self.camera = PiCamera()
        logging.info('Setting up camera...')
        self.camera.resolution = (width, height)
        self.camera.rotation = 180
        self.camera.framerate = 80
        self.camera.exposure_mode = 'auto'
        self.camera.awb_mode = 'auto'
        s = 1.0 / zoom
        p0 = 0.5 - s/2
        p1 = 0.5 + s/2
        self.camera.zoom = (p0, p0, p1, p1)
        time.sleep(2)
        logging.info(f'setup_camera completed: Camera Resolution: {self.camera.MAX_RESOLUTION}')
        logging.info(f' Model: {self.model()}, Zoom: {self.zoom()}')

    def zoom(self):
        z = self.camera.zoom
        return f'({z[0]:.2f}, {z[1]:.2f}, {z[2]:.2f}, {z[3]:.2f})'

    def model(self):
        rev = self.camera.revision
        known = {
            'ov5647': 'V1',
            'imx219': 'V2'
        }
        if rev in known:
            rev = known[rev]
        return rev

    def capture(self):
        logging.debug('Capturing image')
        rawCapture = PiRGBArray(self.camera)
        self.camera.capture(rawCapture, format="bgr")
        image = rawCapture.array
        return image

    def file_capture(self, filename):
        logging.debug(f'snap_picture({filename})')
        self.camera.capture(filename)

