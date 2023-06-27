import argparse
import io
import logging
import os
import signal
import sys
from threading import Condition

from picamera2 import Picamera2
from picamera2.encoders import MJPEGEncoder
from picamera2.outputs import FileOutput
from libcamera import Transform

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
    parser = argparse.ArgumentParser('Simple WebServer')
    parser.add_argument('--port', type=int, default=8888,
                        help='Port for server to listen on')
    parser.add_argument('--logfile', type=str, default='stdout',
                        help='Path of file to write log to. Set to "stdout" to specify console. Default is "stdout"')
    parser.add_argument('--width', '-W', type=int, default=640,
                        help='Width of image')
    parser.add_argument('--height', '-H', type=int, default=480,
                        help='Height of image')
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

def exit_gracefully(signum, frame):
    print(f'SHUTTING DOWN due to {signal.Signals(signum).name}')
    server.call_shutdown()


if __name__ == '__main__':
    config = parse_arguments()
    setup_logging(config.logfile)
    logging.info(f'App Dir: {APP_DIR}')
    logging.info(f'Starting WebServer on port {config.port}')

    # Make a thread safe wrapper for the Picamera2 object?
    # CameraController thread?
    picam2 = Picamera2()
    transform=Transform(hflip=False, vflip=False)
    picam2.configure(picam2.create_video_configuration(main={"size": (config.width, config.height)},
                                                       transform=transform))
    output = StreamingOutput()
    SetupServerHandler.PICAMERA = picam2
    SetupServerHandler.OUTPUT = output
    SetupServerHandler.SENSOR_MODES = picam2.sensor_modes
    picam2.start_recording(MJPEGEncoder(), FileOutput(output))

    try:
        server = WebServer(picam2, SetupServerHandler, port=config.port)
        server.serve_forever(poll_interval=0.5)
    finally:
        picam2.stop_recording()

