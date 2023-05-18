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
    def __init__(self):
        self.not_pi:bool = False

    def status_string(self):
        gpu_str = ''
        v, t = self.check_gpu_temp()
        if v == 'not Pi':
            gpu_str = 'not found'
        else:
            gpu_str = f'temp: {t} ({v})'

        return f'GPU: {gpu_str}'

    def should_throttle_back(self):
        """
        Check system resources and advise on whether it is safe to keep going.
        :return: (status, message) status: 0 - Okay, 1 - Throttle, 2 - Shutdown
        """
        status = 0
        message = 'no issues found'
        v, t = self.check_gpu_temp()
        if v != 'not Pi':
            if v == 'warm' or v == 'hot':
                status = 1
                message = f'GPU Temp: {v}'
            elif v != 'safe':
                status = 2
                message = f'GPU Temp: {v}'
            return status, message
        return status, message

    def check_gpu_temp(self):
        t = self.get_gpu_temp()
        if t is None:
            return 'not Pi', 0
        if t < 80:
            return 'safe', t
        if t < 83:
            return 'warm', t
        if t < 84:
            return 'hot', t
        if t >= 85:
            return 'dangerous', t

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
