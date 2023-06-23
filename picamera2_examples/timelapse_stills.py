#!/usr/bin/python3
import os
import time

from picamera2 import Picamera2

import argparse

parser = argparse.ArgumentParser()
parser.add_argument('--framedir', type=str, default='./frames',
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

print(args)

os.makedirs(args.framedir, exist_ok=True)

picam2 = Picamera2()
camera_config = picam2.create_still_configuration({'size': (args.width, args.height)})
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

start_time = time.time()
for i in range(args.nframes):
    r = picam2.capture_request()
    r.save("main", os.path.join(args.framedir, f"image{i:05}.jpg"))
    r.release()
    print(f"Captured image {i} of {args.nframes} at {time.time() - start_time:.2f}s")


picam2.stop()