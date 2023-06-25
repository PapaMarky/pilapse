#!/usr/bin/python3
import os
import platform
import signal
import sys
import time

from picamera2 import Picamera2
from libcamera import Transform

from datetime import datetime, timedelta
import argparse

TIME_TO_STOP = False
SET_EXPOSURE = False

def get_program_name():
    name = os.path.basename(sys.argv[0])
    s = name.split('.')
    if s[-1] == 'py':
        name = '.'.join(s[:-1])
    return name

def exit_gracefully(signum, frame):
    global TIME_TO_STOP
    TIME_TO_STOP = True
    print(f'{get_program_name()} SHUTTING DOWN due to {signal.Signals(signum).name}')

def do_update_exposure(picam2, controls):
    global SET_EXPOSURE
    exposure_file = '/home/pi/exposure.txt'
    if os.path.exists(exposure_file):
        with open(exposure_file) as f:
            new_exposure = f.read().strip()
            print(f'Setting new exposure time to {new_exposure}')
            controls['ExposureTime'] = int(new_exposure)
            picam2.set_controls(controls)
    SET_EXPOSURE = False

def update_exposure(signum, frame):
    global SET_EXPOSURE
    SET_EXPOSURE = True
    print(f'Update exposure command recieved')

signal.signal(signal.SIGINT, exit_gracefully)
signal.signal(signal.SIGTERM, exit_gracefully)
signal.signal(signal.SIGUSR1, update_exposure)

hostname = platform.node()
frame_path = '/home/pi/exposures/%Y%m%d-timelapse'
parser = argparse.ArgumentParser()
parser.add_argument('--framedir', type=str, default=frame_path,
                    help='Path to directory where frames will be stored')
parser.add_argument('--framerate', type=float, default=1.0,
                    help='Frame rate of camera')
parser.add_argument('--exposure-time', type=int,
                    help='how long to expose each frame')
parser.add_argument('--width', '-W', type=int, default=1920,
                    help='width of each frame')
parser.add_argument('--height', '-H', type=int, default=1080,
                    help='height of each frame')
parser.add_argument('--nframes', '-n', type=int, default=50,
                    help='Number of frames to capture')
args = parser.parse_args()

frame_path = datetime.strftime(datetime.now(), args.framedir)

stop_at = datetime.now()
stop_at = stop_at.replace(hour=5, minute=0, second=0, microsecond=0)
stop_at += timedelta(days=1)
os.makedirs(args.framedir, exist_ok=True)

picam2 = Picamera2()
transform=Transform(hflip=False, vflip=False)
camera_config = picam2.create_still_configuration({'size': (args.width, args.height)}, transform=transform)
picam2.configure(camera_config)
picam2.start()

# Give time for Aec and Awb to settle, before disabling them
time.sleep(1)
controls = {"AeEnable": False, "AwbEnable": False, "FrameRate": args.framerate}
if args.exposure_time is not None:
    controls['ExposureTime'] = args.exposure_time
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
    ts = datetime.strftime(now, '%Y%m%d_%H%M%S.%f')
    image_file = os.path.join(frame_path, f"{ts}.jpg")
    r.save("main", image_file)
    r.release()
    time_remaining = stop_at - now
    print(f"Captured {os.path.basename(image_file)}. Stopping in {timedelta_string(time_remaining)}")
    if TIME_TO_STOP:
        print('Program stopping')
        break
    if SET_EXPOSURE:
        do_update_exposure(picam2, controls)

print(f'Shutting down camera')
picam2.stop()