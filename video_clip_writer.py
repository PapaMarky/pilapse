import argparse
import logging
import os
import threading
import time
from datetime import datetime

from threads import ImageConsumer


class MotionVideoProcessor(ImageConsumer):
    def __init__(self, shutdown_event:threading.Event, config:argparse.Namespace, **kwargs):
        logging.info(f'Creating {type(self)}')
        super().__init__('MotionVideoProcessor', shutdown_event, config, **kwargs)
        self.video_dir:str = None
        self.video_temp:str = self.config.video_temp
        if self.config.video_dir is None:
            self.config.video_dir = self.config.outdir
            self.video_dir = self.config.video_dir
            if '%' in self.video_dir:
                self.video_dir = datetime.strftime(self.now, self.config.video_dir)

    def set_outdir(self):
        super().set_outdir()
        if '%' in self.config.video_dir and self.current_time.minute != self.now.minute:
            logging.info(f'Time (minute) changed, checking outdir')
            self.current_time = self.now
            new_video_dir = datetime.strftime(self.now, self.config.video_dir)
            if new_video_dir != self.video_dir:
                self.video_dir = new_video_dir
                os.makedirs(self.outdir, exist_ok=True)
                logging.info(f'New video dir: {self.video_dir}')

    def do_work(self) -> None:
        self.start_work()
        logging.info(f'Starting Image Writer (do_work for {self.name}) ({self.start_time.strftime("%Y/%m/%d %H:%M:%S")})')
        while True:
            self.now = datetime.now()
            self.set_outdir()

            self.log_status()
            self.check_in_queue()
            if self.check_for_shutdown():
                # this thread runs faster than video producer. give it time to finish
                time.sleep(3)
                self.force_consume = True
                self.check_in_queue()
                break

    def consume_image(self, image):
        path = image['file']
        if not image['motion']:
            logging.debug(f'deleting clip with no motion: {path}')
            os.remove(path)
        elif self.outdir != self.video_temp:
            logging.info(f'Moving {path} to {self.video_dir}')
            out_path = os.path.join(self.video_dir, os.path.basename(path))
            logging.info(f'Moving {path} to {out_path}')
            os.rename(path, out_path)

