from math import log2

import adafruit_veml7700
import board

# https://www.instructables.com/DIY-Photographic-Lightmeter/
class LightMeter:
    def __init__(self):
        self._sensor = adafruit_veml7700.VEML7700(board.I2C())

    def get_EV(self):
        # for ISO = 100
        # lux = (2 ^ ev) * 2.5;
        f_stop = 2.8
        lux = self._sensor.lux
        EV = log2 (lux/2.5)

    def get_sample(self, args):
        success = False
        message = 'VEML7700 Sample'
        data = {}
        try:
            data['light'] = self._sensor.light
            data['lux'] = self._sensor.lux
            success = True
        except Exception as e:
            success = False
            message += ': EXCEPTION: {}'.format(e)
        finally:
            return self.create_response(success, message, data)
