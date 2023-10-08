#!/usr/bin/python3

import argparse
import io
import logging
import os
import sys
import time
from threading import Condition

from picamera2 import Picamera2
Picamera2.set_logging(Picamera2.WARNING)
os.environ['LIBCAMERA_LOG_LEVELS'] = 'ERROR'
from picamera2.encoders import MJPEGEncoder
from picamera2.outputs import FileOutput
from picamera2 import Picamera2, MappedArray
from libcamera import Transform
import cv2
from setup_server_handler import SetupServerHandler
from web_server import WebServer

APP_DIR = os.path.dirname(os.path.abspath(__file__))

def get_program_name():
    name = os.path.basename(sys.argv[0])
    s = name.split('.')
    if s[-1] == 'py':
        name = '.'.join(s[:-1])
    return name

def parse_arguments():
    # TODO : make two versions: still capture and video capture (streaming)
    # Use video for setting up the shot
    # Use still capture for setting exposure time, etc
    parser = argparse.ArgumentParser('Simple WebServer')
    parser.add_argument('--port', type=int, default=8888,
                        help='Port for server to listen on')
    parser.add_argument('--logfile', type=str, default='stdout',
                        help='Path of file to write log to. Set to "stdout" to specify console. Default is "stdout"')
    parser.add_argument('--width', '-W', type=int, default=640,
                        help='Width of image')
    parser.add_argument('--height', '-H', type=int, default=480,
                        help='Height of image')
    parser.add_argument('--exposure-time', type=int,
                        help='Use fixed exposure time instead of auto exposure')
    parser.add_argument('--zoom', type=float,
                        help='Zoom')
    parser.add_argument('--html', type=str, default='html')
    return parser.parse_args()

def setup_logging(logfile):
    #logfile = os.environ.get('LOGFILE')

    if not logfile:
        logfile = f'{get_program_name()}.log'

    if logfile == 'stdout':
        logfile = None

    logfile_name = logfile if logfile is not None else 'stdout'

    print(f'Logging to {logfile_name}')
    logging.basicConfig(
        filename=logfile,
        level=logging.INFO,
        format='%(asctime)s|%(levelname)s|%(threadName)s|%(message)s'
    )

class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()

if __name__ == '__main__':
    config = parse_arguments()
    ar = config.width/config.height
    ar_16_9 = 16/9
    ar_4_3 = 4/3
    d1 = abs(ar-ar_16_9)
    d2 = abs(ar-ar_4_3)
    ar = '4:3' if d1 > d2 else '16:9'
    setup_logging(config.logfile)
    logging.info(f'App Dir: {APP_DIR}')
    logging.info(f'Starting WebServer on port {config.port}')
    logging.info(f'Aspect Ratio: {ar}')


    # Make a thread safe wrapper for the Picamera2 object?
    # CameraController thread?
    picam2 = Picamera2()
    picam2.options["quality"] = 95
    colour = (255, 255, 255)
    origin = (30, 30)
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.3
    thickness = 2
    frame_number = 0
    def apply_timestamp(request):
        global frame_number
        timestamp = f'{frame_number:09}'
        frame_number += 1
        with MappedArray(request, "main") as m:
            cv2.putText(m.array, timestamp, origin, font, scale, colour, thickness)
    picam2.pre_callback = apply_timestamp
    transform=Transform(hflip=False, vflip=False)
    framerate = 0.333 if config.exposure_time is None else 1.0 / (config.exposure_time / 1000000)
    ### TODO look at this example: https://github.com/raspberrypi/picamera2/blob/main/examples/video_with_config.py
    video_config = picam2.create_video_configuration(main={"size": (config.width, config.height)},
                                                     transform=transform)
    controls = video_config['controls']
    if config.zoom > 1.0:
        picam2.start()
        metadata = picam2.capture_metadata()
        print(f'METADATA: {metadata}')

        original_scaler_crop = metadata['ScalerCrop']
        zoom = config.zoom
        print(f'Setting Zoom to {zoom}')
        x, y, w, h = original_scaler_crop
        new_w = w/zoom
        new_h = h/zoom
        new_x = x + w/2 - new_w/2
        new_y = y + h/2 - new_h/2
        controls['ScalerCrop'] = (int(new_x), int(new_y), int(new_w), int(new_h))
        time.sleep(1.0)
        print(f'Zoomed ScalerCrop: {picam2.capture_metadata()["ScalerCrop"]}')
        picam2.stop()
    logging.debug(f'VIDEO CONTROLS: {video_config}')
    picam2.configure(video_config)


    # picam2.video_configuration.controls.FrameRate = 10.0

    output = StreamingOutput()
    SetupServerHandler.PICAMERA = picam2
    SetupServerHandler.OUTPUT = output
    SetupServerHandler.SENSOR_MODES = picam2.sensor_modes
    SetupServerHandler.ASPECT_RATIO = ar
    logging.info(f'Set aspect ratio: {ar}')

    picam2.start_recording(MJPEGEncoder(bitrate=100000000), FileOutput(output))
    time.sleep(1)
    if config.exposure_time is not None:
        logging.info(f'Turning off Auto Exposure. framerate: {framerate}, exposure time: {config.exposure_time}')
        picam2.set_controls(
            {
                # 'FrameRate': 1,
                'FrameDurationLimits': (config.exposure_time, config.exposure_time),
                'ExposureTime': config.exposure_time,
                'AeEnable': False,
                'AwbEnable': False
             }
        )
    logging.debug(f'METADATA: {picam2.capture_metadata()}')

    try:
        logging.info('Starting WebServer')
        server = WebServer(picam2, SetupServerHandler, port=config.port)
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt as k:
        logging.info(f'\nShutting down due to keyboard interrupt')
    finally:
        picam2.stop_recording()

