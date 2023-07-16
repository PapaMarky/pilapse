#!/usr/bin/python3

import argparse
import io
import json
import logging
import os
import signal
import socketserver
import sys
import time
from datetime import datetime
from http import server
from threading import Condition

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from timelapse_server_handler import SetupServerHandler

class WebServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, handler, address='', port=8080):
        super().__init__((address, port), handler)

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
    parser.add_argument('--html', type=str, default='html')
    parser.add_argument('--framedir', type=str, required=True,
                        help='path to where frames are stored (relative to content dir)')
    parser.add_argument('--exposure-time', type=int,
                        help='how long to expose each frame')
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

def exit_gracefully(signum, frame):
    print(f'SHUTTING DOWN due to {signal.Signals(signum).name}')
    server.call_shutdown()

pid_path = '/home/pi/timelapse.txt'
def get_timelapse_pid():
    data = None
    if os.path.exists(pid_path):
        with open(pid_path) as pidfile:
            content = pidfile.read()
            print(f'PID: {content}')
            data = json.loads(content)
    return data

def get_camera_info():
    camera_info_file = '/home/pi/camera_info.json'
    with open(camera_info_file) as f:
        return json.load(f)

class PidMonitorHandler(FileSystemEventHandler):
    def on_modified(self, event):
        time.sleep(0.1)
        timelapse_pid = get_timelapse_pid()
        print(f'Timelapse PID: {timelapse_pid}')
        SetupServerHandler.PID = timelapse_pid



if __name__ == '__main__':
    config = parse_arguments()
    setup_logging(config.logfile)
    logging.info(f'App Dir: {APP_DIR}')
    logging.info(f'Starting WebServer on port {config.port}')
    logging.info(f' - framdir: {config.framedir}')
    SetupServerHandler.FRAME_DIR = datetime.strftime(datetime.now(), config.framedir)

    SetupServerHandler.CAMERA_INFO = get_camera_info()
    timelapse_pid = get_timelapse_pid()
    print(f'timelapse info: {timelapse_pid}')
    SetupServerHandler.PID = timelapse_pid
    event_handler = PidMonitorHandler()
    observer = Observer()
    observer.schedule(event_handler, path=pid_path, recursive=False)
    observer.start()
    controls = {}
    with open('/home/pi/exposure.txt') as f:
        data = json.load(f)
        if 'ExposureTime' in data:
            SetupServerHandler.EXP = int(data['ExposureTime'] * 1000000)

    logging.info(f'FRAME_DIR: {SetupServerHandler.FRAME_DIR}')
    server = WebServer(SetupServerHandler, port=config.port)
    try:
        # TODO: make this aware of TIME_TO_STOP
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
