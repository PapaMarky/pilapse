import logging
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
                 pause=2):
        self._model = None
        self._sensor_mode = None
        self._use_video_port = True

        if aspect_ratio == '4:3':
            self._sensor_mode = 4
        elif aspect_ratio == '16:9':
            self._sensor_mode = 5
        else:
            raise Exception(f'Aspect Ratio should be 4:3 or 16:9. Got {aspect_ratio}')

        self.camera = PiCamera(sensor_mode=self._sensor_mode,
                               framerate_range=(1/10, 40),
                               resolution=(width,height))
        s = 1.0 / zoom
        p0 = 0.5 - s/2
        p1 = 0.5 + s/2
        self.camera.zoom = (p0, p0, p1, p1)
        self.camera.rotation = rotation
        self.camera.exposure_mode = exposure_mode
        self.camera.awb_mode = awb_mode
        self.camera.meter_mode = meter_mode

        try:
            self.camera.led = False
        except:
            logging.info('Failed to turn off LED. Oh well.')

        logging.info(f'Camera {self.model}')
        logging.info(f' -   resolution: {width} x {height}')
        logging.info(f' - aspect ratio: {aspect_ratio}')
        logging.info(f' -         zoom: {zoom}')
        logging.info(f' -     rotation: {rotation}')
        logging.info(f'Sleeping for {pause} seconds to let the sensor find itself')
        time.sleep(pause)

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

    def capture(self) -> PiRGBArray:
        logging.debug('Capturing image')
        rawCapture = PiRGBArray(self.camera)
        self.camera.capture(rawCapture, format="bgr")
        image = rawCapture.array
        return image

    def file_capture(self, filename):
        logging.debug(f'snap_picture({filename})')
        self.camera.capture(filename)

