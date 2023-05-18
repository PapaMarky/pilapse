import argparse
import logging
import re
import subprocess
import threading

import pause

from camera import Camera
from threads import ImageProducer, CameraImage

from datetime import datetime, timedelta
import time


class CameraProducer(ImageProducer):
    # TODO base class producer should be aware of
    #    - "pause" due to run_from / run_until
    #    - stop_at
    #    - nframes
    # or move that control into app?
    def __init__(self, width:int, height:int, zoom:float, prefix:str,
                 shutdown_event:threading.Event, config:argparse.Namespace,
                 **kwargs):
        super(CameraProducer, self).__init__('CameraProducer', shutdown_event, config, **kwargs)
        logging.debug(f'CameraProducer init {self.name}')
        self.width:int = width
        self.height:int = height
        self.prefix:str = prefix
        self.camera:Camera = Camera(width, height, zoom)
        self.nframes:int = 0
        if self.config.framerate:
            self.config.framerate_delta = timedelta(seconds=config.framerate)

        self.nextframe_time = self.now

        self.paused:bool = False if self.config.run_from is None else True

        if self.config.stop_at is not None and isinstance(self.config.stop_at, str):
            logging.debug(f'Setting stop-at: {self.config.stop_at}')
            (hour, minute, second) = self.config.stop_at.split(':')
            self.config.stop_at = datetime.now().replace(hour=int(hour), minute=int(minute), second=int(second), microsecond=0)

        if self.config.run_from is not None:
            logging.debug(f'Setting run-until: {self.config.run_from}')
            self.config.run_from_t = datetime.strptime(self.config.run_from, '%H:%M:%S').time()

        if self.config.run_until is not None:
            logging.debug(f'Setting run-until: {self.config.run_until}')
            self.config.run_until_t = datetime.strptime(self.config.run_until, '%H:%M:%S').time()

        time.sleep(10) # this is really so the camera can warm up

    def get_camera_model(self):
        return self.camera.model()

    def log_status(self):
        # logging.info(f'LOG STATUS: now: {self.now}, report time: {self.report_time}')
        if self.now > self.report_time:
            elapsed = self.now - self.start_time
            elapsed_str = str(elapsed).split('.')[0]
            FPS = self.nframes / elapsed.total_seconds()
            with open('/sys/class/thermal/thermal_zone0/temp') as f:
                temp = int(f.read().strip()) / 1000
            p = subprocess.run(['vcgencmd', 'measure_temp'], capture_output=True)
            t = p.stdout.decode()
            r = r'^temp=([.0-9]+)'
            m = re.match(r, t)
            t = m.group(1) if m is not None else ''

            # logging.info(f'# {os.uname()[1]}: CPU {psutil.cpu_percent()}%, mem {psutil.virtual_memory().percent}%, TEMP CPU: {temp:.1f}C GPU: {t}C')
            logging.info(f'{elapsed_str} frames: {self.nframes} FPS: {FPS:.2f} Qout: {self.out_queue.qsize()}, '
                         f'Paused: {"T" if self.paused else "F"}')
            self.report_time = self.report_time + self.report_wait

    def check_run_until(self):
        # Manage run_from and run_until
        current_time = self.now.time()
        if self.config.run_until is not None and not self.paused:
            logging.debug(f'Run from {self.config.run_from} until {self.config.run_until}')

            if current_time >= self.config.run_until_t or current_time <= self.config.run_from_t:
                logging.info(f'Pausing because outside run time: from {self.config.run_from} until {self.config.run_until}')
                self.paused = True

        if self.paused:
            logging.debug(f'Paused, check the time. now: {self.now.time()}, run from: {self.config.run_from}')
            if current_time >= self.config.run_from_t and current_time <= self.config.run_until_t:
                logging.info(f'Ending pause because inside run time: from {self.config.run_from} until {self.config.run_until}')
                self.paused = False

        if self.paused:
            time.sleep(1)
            return False
        return True

    def check_stop_at(self):
        if self.config.stop_at and self.now > self.config.stop_at:
            logging.info(f'Shutting down due to "stop_at": {self.config.stop_at.strftime("%Y/%m/%d %H:%M:%S")}')
            self.shutdown_event.set()
            return False
        return True

    def preproduce(self):
        if not self.check_run_until():
            logging.debug(f'Run Until Check Failed')
            return False

        if not self.check_stop_at():
            logging.info(f'Stop At Check Failed. Shutting down')
            self.shutdown_event.set()
            return False

        if self.config.nframes is not None and self.nframes > self.config.nframes:
            logging.info(f'nframes ({self.config.nframes}) from config exceeded. Stopping.')
            self.shutdown_event.set()
            return False

        return True
    def produce_image(self) -> str:
        if not self.shutdown_event.is_set():
            if self.out_queue.full():
                logging.warning('Output Queue is full')
                time.sleep(0.001)
                return
            img = CameraImage(self.camera.capture(), prefix=self.prefix, type='png')
            logging.debug(f'captured {img.base_filename}')
            self.out_queue.put(img)
            self.nframes += 1

            if self.config.framerate:
                logging.debug(f'now: {self.now}, delta: {self.config.framerate_delta}')
                self.nextframe_time = self.now + self.config.framerate_delta
                logging.debug(f'nextframe_time: {self.nextframe_time}')
                if self.config.debug:
                    logging.info(f'Pausing until {self.nextframe_time} (framerate:{self.config.framerate})')
                pause.until(self.nextframe_time)
