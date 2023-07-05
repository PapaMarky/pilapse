#!/usr/bin/python3
import json
import logging
import os
import platform
import signal
import sys
import time

from picamera2 import Picamera2
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
if not logfile:
    logfile = f'{get_program_name()}.log'
if logfile == 'stdout':
    logfile = None

print(f'Logging to {logfile}')

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
        print(f'PID: {pid} saved in {pid_path}')

def get_program_name():
    name = os.path.basename(sys.argv[0])
    s = name.split('.')
    if s[-1] == 'py':
        name = '.'.join(s[:-1])
    return name

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
parser.add_argument('--stop-at', type=str, default='05:00:00',
                    help='Stop running when this time is reached. (If this time has already passed today, '
                         'stop at this time tomorrow. Format: HH:MM:SS (24 hour clock)')
args = parser.parse_args()

def exit_gracefully(signum, frame):
    global TIME_TO_STOP
    TIME_TO_STOP = True
    print(f'{get_program_name()} SHUTTING DOWN due to {signal.Signals(signum).name}')

def do_update_exposure(picam2):
    global SET_EXPOSURE
    print(f'Setting controls from exposure.txt')
    if os.path.exists(exposure_file):
        controls = {}
        with open(exposure_file) as f:
            data = json.load(f)
            if 'ExposureTime' in data:
                controls['ExposureTime'] = int(data['ExposureTime'])
                # calculate framerate from new exposure Time
                fps = data['ExposureTime'] / 1000000
                # if fps >
                # controls['FrameRate'] = fps
            if 'Zoom' in data:
                x, y, w, h = original_scaler_crop
                new_w = w/data['Zoom']
                new_h = h/data['Zoom']
                new_x = x + w/2 - new_w/2
                new_y = y + h/2 - new_h/2
                controls['ScalerCrop'] = (int(new_x), int(new_y), int(new_w), int(new_h))


            picam2.set_controls(controls)
            print(f'Setting Controls: {controls}')
    SET_EXPOSURE = False

def update_exposure(signum, frame):
    global SET_EXPOSURE
    SET_EXPOSURE = True
    print(f'Update exposure command recieved')

signal.signal(signal.SIGINT, exit_gracefully)
signal.signal(signal.SIGTERM, exit_gracefully)
signal.signal(signal.SIGUSR1, update_exposure)

if args.zoom is not None and args.zoom < 1.0:
    print('ERROR: zoom must be 1.0 or greater')
    sys.exit(1)

frame_path = datetime.strftime(datetime.now(), args.framedir)


stop_time = args.stop_at.split(':')
hour = stop_time[0]
minute = stop_time[1]
second = stop_time[2]

now = datetime.now()
stop_at = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
if stop_at < now:
    stop_at += timedelta(days=1)
logging.info(f'Timelapse will run until {stop_at.strftime("%H:%m:%s")}')
picam2 = Picamera2()

transform=Transform(hflip=args.flip, vflip=args.flip)
camera_config = picam2.create_still_configuration({'size': (args.width, args.height)}, transform=transform)
picam2.configure(camera_config)
picam2.start()

# Give time for Aec and Awb to settle, before disabling them
time.sleep(3)
print('Turning off Auto Exposure')
controls = {"AeEnable": False, "AwbEnable": False, "FrameRate": args.framerate}
print(f'Setting exposure time to {args.exposure_time}')
if args.exposure_time is not None:
    controls['ExposureTime'] = args.exposure_time

metadata = picam2.capture_metadata()
print(f'METADATA: {metadata}')
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

def timedelta_string(td):
    return str(td).split('.')[0]

print(f'Stopping at {stop_at.strftime("%Y-%m-%d %H:%M:%S")}')
print(f'Saving frames in {frame_path}')
os.makedirs(frame_path, exist_ok=True)
start_time = datetime.now()
i = 0
while True:
    r = picam2.capture_request()
    now = datetime.now()
    if now >= stop_at:
        print('Time to stop')
        break
    metadata = r.get_metadata()
    # print(f'METADATA')
    # print(f'{metadata}')
    lux = metadata['Lux'] if 'Lux' in metadata else 'NOLUX'
    exp_time = metadata['ExposureTime'] if 'ExposureTime' in metadata else 'NOEXP'
    temp = metadata['SensorTemperature'] if 'SensorTemperature' in metadata else '???'
    ts = datetime.strftime(now, '%Y%m%d_%H%M%S.%f')
    image_file = os.path.join(frame_path, f"{ts}_L{lux:.4f}_E{exp_time}.jpg")
    r.save("main", image_file)
    r.release()
    time_remaining = stop_at - now
    print(f"Captured {os.path.basename(image_file)}. Temp: {temp} Stopping in {timedelta_string(time_remaining)}")
    if TIME_TO_STOP:
        print('Program stopping')
        break
    if SET_EXPOSURE:
        do_update_exposure(picam2)

print(f'Shutting down camera')
picam2.stop()