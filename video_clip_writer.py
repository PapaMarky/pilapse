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
        self.converted_clips = 0
        self.deleted_clips = 0
        self.consumed_clips = 0
        self.currently_processing_video = False


    def set_outdir(self):
        if super().set_outdir():
            logging.info(f'Time (minute) changed, checking outdir')
            new_video_dir = datetime.strftime(self.now, self.config.video_dir)
            if new_video_dir != self.video_dir:
                self.video_dir = new_video_dir
                os.makedirs(self.outdir, exist_ok=True)
                logging.info(f'New video dir: {self.video_dir}')
                return True
            return False

    def log_status(self):
        if self.now > self.report_time:
            logging.info(f'Q: {self.in_queue.qsize()}, total: {self.consumed_clips} assembled: {self.converted_clips} '
                         f'deleted: {self.deleted_clips} processing: {self.currently_processing_video}')
            self.report_time = self.report_time + self.report_wait

    def do_work(self) -> None:
        self.start_work()
        logging.info(f'Starting Video Writer (do_work for {self.name}) ({self.start_time.strftime("%Y/%m/%d %H:%M:%S")})')
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
        # TODO move this to one or more separate worker threads
        new_path = os.path.splitext(clip.filename)[0] + '.mov'
        self.currently_processing_video = True
        file_number = 0
        filename = clip._filelist[file_number]
        video_in = cv2.VideoCapture(filename)
        frame_width = int(video_in.get(cv2.CAP_PROP_FRAME_WIDTH))
        frame_height = int(video_in.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = int(video_in.get(cv2.CAP_PROP_FPS)) if clip.framerate is None else int(clip.framerate)
        logging.info(f'Assembling {os.path.basename(filename)} (FPS: {fps})')
        logging.info(f' start: {clip.start_time.strftime("%Y%m%d_%H%M%S.%f")} end: {clip.end_time.strftime("%Y%m%d_%H%M%S.%f")}')
        logging.info(f' motion: {clip.first_motion.strftime("%Y%m%d_%H%M%S.%f")} - {clip.last_motion.strftime("%Y%m%d_%H%M%S.%f")}')
        for file in clip._filelist:
            logging.info(f' - {os.path.basename(file)}')

        capSize = (frame_width, frame_height) # this is the size of my source video
        fourcc = cv2.VideoWriter_fourcc('m', 'p', '4', 'v') # note the lower case
        video_out = cv2.VideoWriter()
        success = video_out.open(new_path, fourcc, fps, capSize)
        if not success:
            logging.error(f'Failed to open file for converted video: {new_path}')
            return
        frame_count = 0

        while True:
            success, frame = video_in.read()
            if not success:
                # assume we hit the end of the video clip we are converting
                file_number += 1
                if file_number < len(clip._filelist):
                    if frame_count % 10 == 0:
                        self.log_status()
                    os.remove(filename)
                    video_in.release()
                    video_in = None
                    filename = clip._filelist[file_number]
                    logging.info(f'Appending clip: {filename} (at {frame_count} frames)')
                    video_in = cv2.VideoCapture(filename)
                    success, frame = video_in.read()
                    if not success:
                        logging.error('Could not read first frame from next clip')
                        break
                else:
                    break
            frame_count += 1
            video_out.write(frame)

        os.remove(filename)
        # delete the incoming clip
        video_in.release()
        video_out.release()
        logging.info(f'Converted {frame_count} frames, {frame_count/fps:.2f} seconds')
        self.converted_clips += 1
        self.currently_processing_video = False
        return new_path

    def consume_image(self, clip:VideoClip):
        self.consumed_clips += 1
        path = clip.filename
        if not clip.has_motion:
            logging.debug(f'deleting clip with no motion: {path}')
            os.remove(path)
            self.deleted_clips += 1
        elif self.outdir != self.video_temp:
            clip_path = self.convert_video(clip) # This needs to happen even when temp and out dirs are the same
            if clip_path is not None:
                logging.info(f'Saving {os.path.basename(clip_path)}')
                out_path = os.path.join(self.video_dir, os.path.basename(clip_path))
                logging.info(f'Moving {clip_path} to {out_path}')
                os.rename(clip_path, out_path)

