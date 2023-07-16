#!/usr/bin/python3
import json
import logging
import os
import platform
import signal
import sys
import time

import picamera2
from picamera2 import Picamera2
Picamera2.set_logging(Picamera2.WARNING)
os.environ['LIBCAMERA_LOG_LEVELS'] = 'ERROR'
from libcamera import Transform

from datetime import datetime, timedelta
import argparse
def get_program_name():
    name = os.path.basename(sys.argv[0])
    s = name.split('.')
    if s[-1] == 'py':
        name = '.'.join(s[:-1])
    return name


logfile = os.environ.get('LOGFILE')

print(f'Logging to {logfile}')

if not logfile or logfile == 'stdout':
    logfile = None

logging.basicConfig(
    filename=logfile,
    level=logging.INFO,
    format='%(asctime)s|%(levelname)s|%(threadName)s|%(message)s'
)

TIME_TO_STOP = False
SET_EXPOSURE = False

pid_path = '/home/pi/timelapse.txt'
exposure_file = '/home/pi/exposure.txt'

def set_timelapse_pid():
    with open(pid_path, 'w') as pidout:
        pid = os.getpid()
        pidout.write(f'{pid}')
        logging.info(f'PID: {pid} saved in {pid_path}')

def get_program_name():
    name = os.path.basename(sys.argv[0])
    s = name.split('.')
    if s[-1] == 'py':
        name = '.'.join(s[:-1])
    return name

def get_camera_model(picam2):
    if picam2 is None:
        return 'None'
    m = picam2.global_camera_info()[0]['Model']
    known = {
        'ov5647': 'V1',
        'imx219': 'V2',
        'imx477': 'HQ',
        'imx708_wide': 'V3-wide'
    }
    if m in known:
        return known[m]
    return m

def get_sensor_modes(picam2):
    if picam2 is None:
        return {}
    sensor_modes = []
    for mode in picam2.sensor_modes:
        m = {}
        for field in mode:
            if isinstance(mode[field], picamera2.sensor_format.SensorFormat):
                m[field] = str(mode[field])
            else:
                m[field] = mode[field]
        sensor_modes.append(m)
    return sensor_modes

def save_camera_info(picam2):
    camera_info_file = '/home/pi/camera_info.json'
    camera_info = {
        'model': get_camera_model(picam2),
        'sensor_modes': get_sensor_modes(picam2)
    }
    with open(camera_info_file, 'w') as f:
        json.dump(camera_info, f, indent=4)

hostname = platform.node()
frame_path = '/home/pi/exposures/%Y%m%d-timelapse'
parser = argparse.ArgumentParser()
parser.add_argument('--framedir', type=str, default=frame_path,
                    help='Path to directory where frames will be stored')
parser.add_argument('--framerate', type=float, default=1.0,
                    help='Frame rate of camera')
parser.add_argument('--calc-framerate', action='store_true',
                    help='When exposure time is changed via signal, make the framerate match')
parser.add_argument('--exposure-time', type=int,
                    help='how long to expose each frame')
parser.add_argument('--width', '-W', type=int, default=1920,
                    help='width of each frame')
parser.add_argument('--height', '-H', type=int, default=1080,
                    help='height of each frame')
parser.add_argument('--nframes', '-n', type=int, default=50,
                    help='Number of frames to capture')
parser.add_argument('--zoom', type=float, default=1.0,
                    help='Zoom. must be 1.0 or greater')
parser.add_argument('--flip', action='store_true',
                    help='flip the image over. (use this if the images are upside down)')
parser.add_argument('--stop-at', type=str,
                    help='Stop running when this time is reached. If this time has already passed today, '
                         'stop at this time tomorrow. Format: HH:MM:SS (24 hour clock). '
                         'If this is not set, timelapse will run forever or until killed with signal')
parser.add_argument('--singleshot', action='store_true',
                    help='Instead of timelapsing, only take a picture when SIGUSR2 is recieved. '
                         '(for setting up and experimenting')
args = parser.parse_args()

class MetaDataLog:
    def __init__(self, filepath):
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        self._file = open(filepath, 'w')

    def __del__(self):
        self._file.flush()
        self._file.close()

    def addline(self, line):
        self._file.write(line)
        if not line.endswith('\n'):
            self._file.write('\n')
        self._file.flush()

logging.info(f'Framedir: {args.framedir}')
metadata_log_file =os.path.join(os.path.dirname(args.framedir), f'{os.path.basename(args.framedir)}-metadata.log')
logging.info(f'Metadata log: {metadata_log_file}')
metalog = MetaDataLog(metadata_log_file)

def timedelta_formatter(td:timedelta):
    #  TODO : move to library
    td_sec = td.seconds
    hour_count, rem = divmod(td_sec, 3600)
    minute_count, second_count = divmod(rem, 60)
    msg = f'{hour_count:02}:{minute_count:02}:{second_count:02}'
    if td.days > 0:
        day_str = f'{td.days} day'
        if td.days > 1:
            day_str += 's'
        day_str += ' '
        msg = day_str + msg
    return msg

def exit_gracefully(signum, frame):
    global TIME_TO_STOP
    TIME_TO_STOP = True
    logging.info(f'{get_program_name()} SHUTTING DOWN due to {signal.Signals(signum).name}')

def do_update_exposure(picam2):
    global SET_EXPOSURE
    logging.info(f'Setting controls from exposure.txt')
    if os.path.exists(exposure_file):
        controls = {}
        with open(exposure_file) as f:
            data = json.load(f)
            if 'ExposureTime' in data:
                controls['ExposureTime'] = int(data['ExposureTime'])
                print(f'data: {data}')
                # calculate framerate from new exposure Time
                fps = data['ExposureTime'] / 1000000
                # if fps >
                controls['FrameDurationLimits'] = (int(data['ExposureTime']), int(data['ExposureTime']))
                controls["AeEnable"] = False
                controls["AwbEnable"] =  False
                logging.info(f'New settings: Exposure time: {data["ExposureTime"]}, FPS: {fps}')
            if 'Zoom' in data:
                x, y, w, h = original_scaler_crop
                new_w = w/data['Zoom']
                new_h = h/data['Zoom']
                new_x = x + w/2 - new_w/2
                new_y = y + h/2 - new_h/2
                controls['ScalerCrop'] = (int(new_x), int(new_y), int(new_w), int(new_h))


            picam2.set_controls(controls)
            logging.info(f'Setting Controls: {controls}')
    SET_EXPOSURE = False

def update_exposure(signum, frame):
    global SET_EXPOSURE
    SET_EXPOSURE = True
    logging.info(f'Update exposure command recieved')

signal.signal(signal.SIGINT, exit_gracefully)
signal.signal(signal.SIGTERM, exit_gracefully)
signal.signal(signal.SIGUSR1, update_exposure)

if args.zoom is not None and args.zoom < 1.0:
    logging.error('zoom must be 1.0 or greater')
    sys.exit(1)

frame_path = datetime.strftime(datetime.now(), args.framedir)

if args.stop_at is not None:
    stop_time = args.stop_at.split(':')
    hour = int(stop_time[0])
    minute = int(stop_time[1])
    second = int(stop_time[2])

    now = datetime.now()
    stop_at = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
    if stop_at < now:
        logging.warning(f'{stop_at} is in the past. Assuming you mean tomorrow and adjusting...')
        stop_at += timedelta(days=1)
else:
    stop_at = None

picam2 = Picamera2()
save_camera_info(picam2)

transform=Transform(hflip=args.flip, vflip=args.flip)
camera_config = picam2.create_still_configuration({'size': (args.width, args.height)}, transform=transform)
picam2.configure(camera_config)
picam2.start()

# Give time for Aec and Awb to settle, before disabling them
time.sleep(3)
logging.info(f'Setting Framerate: {args.framerate}')
controls = {"FrameRate": args.framerate}
logging.info(f'Setting exposure time to {args.exposure_time}')
if args.exposure_time is not None:
    logging.info('Turning off Auto Exposure')
    controls['ExposureTime'] = args.exposure_time
    controls["AeEnable"] = False
    controls["AwbEnable"] =  False

metadata = picam2.capture_metadata()
logging.info(f'METADATA: {metadata}')
original_scaler_crop = metadata['ScalerCrop']
set_timelapse_pid()
fps = metadata['ExposureTime'] / 1000000
with open(exposure_file, 'w') as f:
    data = {
        'Zoom': float(args.zoom),
        'ExposureTime': fps
    }
    f.write(json.dumps(data))

if args.zoom is not None:
    x, y, w, h = original_scaler_crop
    new_w = w/args.zoom
    new_h = h/args.zoom
    new_x = x + w/2 - new_w/2
    new_y = y + h/2 - new_h/2
    controls['ScalerCrop'] = (int(new_x), int(new_y), int(new_w), int(new_h))

picam2.set_controls(controls)
# And wait for those settings to take effect
time.sleep(1)
metadata = picam2.capture_metadata()
logging.info(f'METADATA: {metadata}')

def capture_image():
    r = picam2.capture_request()
    metadata = r.get_metadata()
    lux = metadata['Lux'] if 'Lux' in metadata else 'NOLUX'
    exp_time = metadata['ExposureTime'] if 'ExposureTime' in metadata else 'NOEXP'
    ts = datetime.strftime(now, '%Y%m%d_%H%M%S.%f')
    image_file = os.path.join(frame_path, f"{ts}_L{lux:.4f}_E{exp_time}.jpg")
    r.save("main", image_file)
    r.release()
    image_base_name = os.path.basename(image_file)
    metalog.addline(f'{image_base_name} | {metadata}')
    time_remaining_string = '' if stop_at is None else f' Stopping in {timedelta_string(stop_at - now)}'
    logging.info(f"Captured {image_base_name}. {time_remaining_string}")

logging.info(f'Setting up signal handler for single shot mode')
def take_single_shot(signum, frame):
    if args.singleshot:
        logging.info('Processing Request for SingleShot...')
        capture_image()
    else:
        logging.info('Singleshot request recieved, but not in singleshot mode. Ignoring request.')

signal.signal(signal.SIGUSR2, take_single_shot)

def timedelta_string(td):
    return str(td).split('.')[0]

if stop_at is not None:
    logging.info(f'Timelapse will stop at {stop_at.strftime("%Y-%m-%d %H:%M:%S")} '
          f'(Time from now: {timedelta_formatter(stop_at - now)})')
logging.info(f'Saving frames in {frame_path}')
os.makedirs(frame_path, exist_ok=True)
start_time = datetime.now()
i = 0
logging.info(f'READY FOR HELPER')
while True:
    now = datetime.now()
    if stop_at is not None and now >= stop_at:
        logging.info(f'Stop time {args.stop_at} reached...')
        break
    if args.singleshot:
        time.sleep(1)
    else:
        capture_image()

    if TIME_TO_STOP:
        logging.info('Program stopping')
        break

    if SET_EXPOSURE:
        do_update_exposure(picam2)

logging.info(f'Shutting down camera')
picam2.stop()