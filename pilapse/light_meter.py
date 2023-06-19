import logging
from math import log2

import adafruit_veml7700
import board

# https://www.instructables.com/DIY-Photographic-Lightmeter/
class LightMeter:
    def __init__(self):
        self._sensor = None
        try:
            self._sensor = adafruit_veml7700.VEML7700(board.I2C())
        except Exception as e:
            logging.warning(f'Failed to set up light sensor. Will go on without it.')
            logging.warning(e)

    @property
    def lux(self):
        lux = self._sensor.lux if self._sensor is not None else None
        return lux

    @property
    def available(self):
        return self._sensor is not None

