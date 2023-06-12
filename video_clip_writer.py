import argparse
import logging
import os
import threading
import time
from datetime import datetime

import cv2

from threads import ImageConsumer
from video_clip import VideoClip


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
        logging.info(f'config video dir: {self.config.video_dir}')
        logging.info(f'       video dir: {self.video_dir}')


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

    def convert_video(self, clip:VideoClip):
        new_path = os.path.splitext(clip.filename)[0] + '.mov'

        file_number = 0
        filename = clip._filelist[file_number]
        video_cap = cv2.VideoCapture(filename)
        frame_width = int(video_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(video_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = int(video_cap.get(cv2.CAP_PROP_FPS))
        logging.info(f'converting {filename} to {new_path} (FPS: {fps})')
        logging.info(f'files: {clip._filelist}')

        capSize = (frame_width, frame_height) # this is the size of my source video
        fourcc = cv2.VideoWriter_fourcc('m', 'p', '4', 'v') # note the lower case
        video = cv2.VideoWriter()
        success = video.open(new_path, fourcc, fps, capSize)
        if not success:
            raise Exception(f'Failed to open file for converted video: {new_path}')

        frame_count = 0

        while True:
            success, frame = video_cap.read()
            if not success:
                # assume we hit the end of the video clip we are converting
                file_number += 1
                if file_number < len(clip._filelist):
                    filename = clip._filelist[file_number]
                    logging.info(f'Appending clip: {filename}')
                    video_cap = cv2.VideoCapture(filename)
                    success, frame = video_cap.read()
                    if not success:
                        logging.error('Could not read first frame from next clip')
                        break
                break
            frame_count += 1
            video.write(frame)

        os.remove(clip.filename)
        # delete the incoming clip
        video_cap.release()
        video.release()
        logging.info(f'Converted {frame_count} frames, {frame_count/fps:.2f} seconds')
        return new_path

    def consume_image(self, clip:VideoClip):
        path = clip.filename
        if not clip.has_motion:
            logging.debug(f'deleting clip with no motion: {path}')
            os.remove(path)
        elif self.outdir != self.video_temp:
            clip_path = self.convert_video(clip)
            logging.info(f'Saving {os.path.basename(clip_path)}')
            out_path = os.path.join(self.video_dir, os.path.basename(clip_path))
            logging.info(f'Moving {clip_path} to {out_path}')
            os.rename(clip_path, out_path)

