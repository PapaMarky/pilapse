"""
Monitor system resources for problems

* Memory
* Disk Space
* CPU usage
* CPU temp
* GPU temp

"""
import logging
import os.path
import re
import subprocess


class SystemResources:

    GPU_TEMP_PATH = ''
    GPU_COMMAND = '/usr/bin/vcgencmd'
    LOW_V = '/sys/devices/platform/soc/soc:firmware/get_throttled'
    def __init__(self):
        self.not_pi:bool = False
        self.need_to_cool = False
        # remember the model
        with open('/proc/device-tree/model') as f:
            self._model:str = f.read()
            if self._model.endswith('\x00'):
                self._model = self._model[:-1]

    @property
    def model(self):
        return self._model

    def status_string(self):
        gpu_str = ''
        v, t = self.check_gpu_temp()
        if v == 'not Pi':
            gpu_str = 'not found'
        else:
            gpu_str = f'temp: {t} ({v})'

        return f'GPU: {gpu_str}'

    def should_shutdown(self):
        if self.check_for_undercurrent():
            return True
        return False

    def should_throttle_back(self):
        """
        Check system resources and advise on whether it is safe to keep going.
        :return: (status, message) status: 0 - Okay, 1 - Throttle, 2 - Shutdown
        """
        status = 0
        message = 'no issues found'
        v, t = self.check_gpu_temp()
        # v will be one of "not Pi", cool, safe, warm, hot, dangerous
        if v != 'not Pi':
            if v == 'dangerous':
                status = 2
            if v == 'warm' or v == 'hot':
                status = 1
                self.need_to_cool = True
            elif v == 'safe':
                status = 1 if self.need_to_cool else 0
                message = f'GPU Temp: {v}'
            elif v == 'cool':
                status = 0
                self.need_to_cool = False
            else:
                message = f'GPU Temp: {v} ({t})'
            return status, message
        return status, message

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

    def check_gpu_temp(self):
        t = self.get_gpu_temp()
        if t is None:
            return 'not Pi', 0
        if t < 75:
            return 'cool', t
        if t < 80:
            return 'safe', t
        if t < 83:
            return 'warm', t
        if t < 85:
            return 'hot', t
        if t >= 85:
            return 'dangerous', t
        return 'crazy', t

    def get_gpu_temp(self):
        if self.not_pi:
            return None
        if not os.path.exists(self.GPU_COMMAND):
            if not self.not_pi:
                logging.warning('This is not a Raspberry Pi. Cannot check GPU')
                self.not_pi = True
            return None
        try:
            p = subprocess.run(['vcgencmd', 'measure_temp'], capture_output=True)
            t = p.stdout.decode()
            r = r'^temp=([.0-9]+)'
            m = re.match(r, t)
            if not m:
                logging.error(f'Bad message from {self.GPU_COMMAND}: "{t}"')
                return None
            t = m.group(1) if m is not None else '0'
            t = float(t)
            return t
        except Exception as e:
            logging.exception(f'Exception while getting GPU temp: {e}')
            return None
