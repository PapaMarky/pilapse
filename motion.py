#! /usr/bin/env python3

import argparse
import threading
from pilapse.camera_producer import CameraProducer

from pilapse.config import Configurable
import pilapse as pl
from queue import Queue
from pilapse.threads import DirectoryProducer, MotionPipeline, ImageWriter

import logging
import time

from pilapse.video_clip_writer import MotionVideoProcessor


def BGR(r, g, b):
    return (b, g, r)

BLUE = BGR(0, 0, 255)
GREEN = BGR(0, 255, 0)
RED = BGR(255, 0, 0)
CYAN = BGR(0, 255, 255)
MAGENTA = BGR(255, 0, 255)
YELLOW = BGR(255, 255, 0)
ORANGE = BGR(255,165,0)
WHITE = BGR(255, 255, 255)

class MotionDetectionApp(Configurable):

    ARGS_ADDED = False
    @classmethod
    def add_arguments_to_parser(cls, parser:argparse.ArgumentParser, argument_group_name:str='Motion Settings')->argparse.ArgumentParser:
        logging.info(f'Adding {cls.__name__} args to parser (ADDED:{cls.ARGS_ADDED})')
        if cls.ARGS_ADDED:
            return parser

        motion = parser.add_argument_group(argument_group_name, 'Parameters related to motion detection')
        motion.add_argument('--mindiff', '-m', type=int, help='Minimum size of "moving object" to detect', default=75)
        motion.add_argument('--top', '-t', type=float, help='top of region of interest. (0.0 - 1.0) '
                                                            'Ignore any motion above this',
                            default=0.0)
        motion.add_argument('--bottom', '-b', type=float, help='bottom of region of interest. (0.0 - 1.0) '
                                                               'Ignore any motion below this',
                            default=1.0)
        motion.add_argument('--left', '-l', type=float, help='left of region of interest. (0.0 - 1.0) '
                                                             'Ignore any motion left of this',
                            default=0.0)
        motion.add_argument('--right', '-r', type=float,
                            help='right of region of interest. (0.0 - 1.0) '
                                 'Ignore any motion to the right of this',
                            default=1.0)
        motion.add_argument('--shrinkto', type=float,
                            help='Shrink images to this height for analysis. This can speed up analysis. '
                                 'If this value is a float, it will be interpreted as percentage', default=None)
        motion.add_argument('--threshold', type=int,
                            help='cut off threshold for detecting changes (0 - 255)',
                            default=25)
        motion.add_argument('--dilation', type=int, default=3,
                            help='Number of dilation iterations to perform')
        motion.add_argument('--save-diffs', action='store_true',
                               help='also save the diffed images for debugging')
        motion.add_argument('--show-motion', action='store_true',
                               help='Highlight motion in output images.')
        motion.add_argument('--testframe', action='store_true',
                               help='Write a test frame with layout information.')
        motion.add_argument('--testframe-nogrid', action='store_true',
                            help='Write a test frame without layout information.')

        motion.add_argument('--all-frames', action='store_true',
                           help='Save all images even when no motion is detected')

        motion.add_argument('--video', action='store_true',
                            help='capture video clips of motion when detected')
        motion.add_argument('-video-temp', type=str, default='~/.pilapse/video-temp',
                            help='Temporary directory where unprocessed video clips will be stored')
        motion.add_argument('--video-dir', type=str,
                            help='Directory where processed video clips will be stored. Defaults to same location '
                                 'as where still images are stored')
        motion.add_argument('--nightsky', help=argparse.SUPPRESS, default=False)

        cls.ARGS_ADDED = True
        # Add the args of Configurables that MotionDetectionApp uses
        CameraProducer.add_arguments_to_parser(parser)
        DirectoryProducer.add_arguments_to_parser(parser)
        ImageWriter.add_arguments_to_parser(parser)

        return parser

    def __init__(self):
        self._version = '1.0.0'
        self._camera_producer:CameraProducer = None
        self._directory_producer:DirectoryProducer = None
        self._motion_pipeline:MotionPipeline = None
        self._image_writer:ImageWriter = None
        self._video_writer:MotionVideoProcessor = None

        parser = Configurable.create_parser('Motion Detection App for Raspberry Pi')
        self._parser = MotionDetectionApp.add_arguments_to_parser(parser)
        self._config = self.load_from_list(self._parser)
        MotionDetectionApp.validate_config(self._config)

        if not pl.it_is_time_to_die():
            self.process_config(self._config)
            self.front_queue = Queue()
            self.back_queue = Queue()
            self.motion_event_queue = Queue() if self._config.video else None
            self.video_clip_queue = Queue() if self._config.video else None
            logging.info(f'Motion Event Queue: {self.motion_event_queue}')
            self._shutdown_event = threading.Event()

    def load_from_list(self, parser, arglist=None):
        logging.info('loading MOTION config from list:')

        config = super().load_from_list(parser, arglist=arglist)
        self.dump_to_log(config)

        return config

    def process_config(self, config):
        logging.debug(f'CONFIG: {config}')
        super().process_config(config)

        self.bottom = int(self._config.bottom * self._config.height)
        self.top = int(self._config.top * self._config.height)
        self.left = int(self._config.left * self._config.width)
        self.right = int(self._config.right * self._config.width)

        if self._config.shrinkto is not None:
            logging.debug('shrinkto is set')
            if self._config.shrinkto <= 1.0:
                self.shrinkto = int(self._config.height * self._config.shrinkto)

    def run(self):
        if pl.it_is_time_to_die():
            return
        ###
        # Create a Motion Consumer and Image Producer. Start them up.

        if self._config.video:
            video_writer = MotionVideoProcessor(self._shutdown_event, self._config, in_queue=self.video_clip_queue)
            self._video_writer = video_writer

        if self._config.source_dir:
            # load images from directory
            producer = DirectoryProducer('jpg', self._shutdown_event, self._config, out_queue=self.front_queue)
            self._directory_producer = producer
        else:
            # create images using camera

            producer = CameraProducer(self._shutdown_event, self._config,
                                      out_queue=self.front_queue,
                                      motion_event_queue=self.motion_event_queue,
                                      video_clip_queue=self.video_clip_queue
                                      )
            self._camera_producer = producer
        self._motion_pipeline = MotionPipeline(self._shutdown_event, self._config,
                                               in_queue=self.front_queue,
                                               out_queue=self.back_queue,
                                               motion_event_queue=self.motion_event_queue)


        self._image_writer = ImageWriter(self._shutdown_event, self._config, in_queue=self.back_queue)

        self._image_writer.start()
        self._motion_pipeline.start()
        if self._video_writer is not None:
            self._video_writer.start()
        producer.start()

        while True:
            logging.debug(f'waiting: producer alive? {producer.is_alive()}, consumer alive? '
                          f'{self._motion_pipeline.is_alive()} writer alive? {self._image_writer.is_alive()}')
            if not producer.is_alive() or not self._motion_pipeline.is_alive() or not self._image_writer.is_alive():
                self._shutdown_event.set()
                pl.set_time_to_die()

            if pl.it_is_time_to_die():
                logging.info('Shutting down')
                self._shutdown_event.set()
                break

                logging.info('Waiting for producer...')
                try:
                    producer.join(5.0)
                    if producer.is_alive():
                        logging.warning('- Timed out, producer is still alive.')
                except Exception as e:
                    logging.exception(e)

                logging.info('Waiting for pipeline...')
                try:
                    pipeline.join(5.0)
                    if pipeline.is_alive():
                        logging.warning('- Timed out, pipeline is still alive.')
                except Exception as e:
                    logging.exception(e)

                logging.info('Waiting for image writer...')
                try:
                    writer.join(5.0)
                    if writer.is_alive():
                        logging.warning('- Timed out, writer is still alive.')
                except Exception as e:
                    logging.exception(e)

                break
                logging.info('Waiting for video writer...')
                try:
                    video_writer.join(5.0)
                    if video_writer.is_alive():
                        logging.warning('- Timed out, video_writer is still alive.')
                except Exception as e:
                    logging.exception(e)

                break

            self._shutdown_event.wait(1)
            if self._shutdown_event.is_set():
                pl.set_time_to_die()
                break
        pl.die()

def main():
    try:
        app = MotionDetectionApp()
        if not pl.create_pid_file():
            pl.die()
        if not pl.it_is_time_to_die():
            app.run()
    except Exception as e:
        logging.exception('Exception in Main')
        logging.exception(e)
        pl.die(1)

if __name__ == '__main__':
    try:
        main()
        if pl.it_is_time_to_die():
            logging.info('Exiting: Graceful shutdown')
    except Exception as e:
        logging.exception(f'Unhandled Exception: {e}')
        pl.die(1)