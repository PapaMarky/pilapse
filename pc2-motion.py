#!/usr/bin/python3
import argparse
import os
import signal
import sys

import time
import math
from datetime import datetime, timedelta

import cv2
import numpy as np

from picamera2 import Picamera2, MappedArray
Picamera2.set_logging(Picamera2.WARNING)
os.environ['LIBCAMERA_LOG_LEVELS'] = 'ERROR'

from picamera2.encoders import H264Encoder
from picamera2.outputs import CircularOutput
import libcamera

TIME_TO_STOP = False

def get_program_name():
    name = os.path.basename(sys.argv[0])
    s = name.split('.')
    if s[-1] == 'py':
        name = '.'.join(s[:-1])
    return name

def exit_gracefully(signum, frame):
    global TIME_TO_STOP
    TIME_TO_STOP = True
    print(f'\n{get_program_name()} SHUTTING DOWN due to {signal.Signals(signum).name}')

signal.signal(signal.SIGINT, exit_gracefully)
signal.signal(signal.SIGTERM, exit_gracefully)

mse = 0
colour = (0, 255, 0)
origin = (0, 60)
font = cv2.FONT_HERSHEY_SIMPLEX
scale = 1
thickness = 2

parser = argparse.ArgumentParser('Simple video motion capture based on Picamera2')
parser.add_argument('--exposure', type=int,
                    help='force the exposure speed (Microseconds). If fps frequent, it will be reduced')
parser.add_argument('--fps', type=float, default=30,
                    help='output video frames per second. If this is too high for the requested exposure time, '
                         'fps will be reduced. Default: 30.')
parser.add_argument('--mse', type=float, default=7.0,
                    help='Sensitivity to motion (mean square error). If something like wind is triggering motion, '
                         'try setting this to a higher value. Actual values are logged to give you an idea of what '
                         'to set it to. If you make this value too low, noise will cause constant motion detection. '
                         'Default: 7.0')
parser.add_argument('--zoom', type=float, default=1.0,
                    help='Digital zoom value to apply to camera. Default 1.0 (no zoom)')
parser.add_argument('--flip', action='store_true',
                    help='Rotate image 180 degrees. Use this if your videos are upside down.')
args = parser.parse_args()

debug = True
def add_mse(request):
    with MappedArray(request, "main") as m:
        cv2.putText(m.array, f'{mse:.2f}', origin, font, scale, colour, thickness)

lsize = (320, 240)
picam2 = Picamera2()
exp = args.exposure
fps = args.fps
controls={}
if args.exposure is not None:
    maxfps = exp / 1000000
    if fps > maxfps:
        print(f'WARNING: fps is too fast. Setting to {maxfps:.4f}')
        fps = maxfps
    controls={"FrameDurationLimits": (exp, exp),
              "ExposureTime": exp,
              }

MAX_MSE = args.mse

video_config = picam2.create_video_configuration(
    main={"size": (1920, 1080), "format": "RGB888"},
    lores={"size": lsize, "format": "YUV420"},
    controls=controls
)
video_config['transform'] = libcamera.Transform(hflip=args.flip, vflip=args.flip)
picam2.configure(video_config)

picam2.start_preview()
encoder = H264Encoder(10000000, repeat=True)
# 5 seconds X FramesPerSecond
BUFFER_SIZE = math.ceil(5 * fps)
print(f'BUFFER_SIZE = {BUFFER_SIZE} (fps: {fps}) MSE Threshold: {MAX_MSE}')
encoder.output = CircularOutput()
picam2.encoder = encoder
picam2.post_callback = add_mse
picam2.start()
picam2.start_encoder()
metadata = picam2.capture_metadata()
print(f'METADATA: {metadata}')

if args.zoom > 1.0:
    original_scaler_crop = metadata['ScalerCrop']
    zoom = args.zoom
    print(f'Setting Zoom to {zoom}')
    x, y, w, h = original_scaler_crop
    new_w = w/zoom
    new_h = h/zoom
    new_x = x + w/2 - new_w/2
    new_y = y + h/2 - new_h/2
    picam2.set_controls({
        'ScalerCrop': (int(new_x), int(new_y), int(new_w), int(new_h))
    })
    time.sleep(1.0)
    print(f'Zoomed ScalerCrop: {picam2.capture_metadata()["ScalerCrop"]}')

w, h = lsize
prev = None
encoding = False
ltime = 0
end_time = None
end_time_offset = timedelta(seconds=5)
now = datetime.now()
outdir = now.strftime('/home/pi/exposures/%Y%m%d-motion2')
os.makedirs(outdir, exist_ok=True)
file_basename = ''

print('- BEGINNING MOTION DETECTION AND CAPTURE -')

while True:
    if TIME_TO_STOP:
        print('Shutting down...')
        break
    cur = picam2.capture_buffer("lores")
    cur = cur[:w * h].reshape(h, w)
    # TODO : define area of interest (top, bottom, left, right) and crop each frame
    #  then compare just the "cropped" parts
    # EX: cropped_image = img[Y:Y+H, X:X+W]
    # Optionally use post_callback to add rectangle on output in the setup tool

    # Create an overlay with the MSE for debugging
    if prev is not None:
        now = datetime.now()
        # Measure pixels differences between current and
        # previous frame
        mse = np.square(np.subtract(cur, prev)).mean()
        if mse > MAX_MSE:
            if not encoding:
                # if we start recording immediately we get a 5 second lead. consider waiting 2 seconds.
                max_mse = mse
                file_basename = f"{now.strftime('%Y%m%d-%H%M%S.%f')}_motion_{mse:.1f}"
                outfile = os.path.join(outdir, f"{file_basename}.h264")
                encoder.output.fileoutput = outfile
                encoder.output.start()
                encoding = True
                print(f'Motion Detected: {outfile}, mse: {mse}')
            else:
                if mse > max_mse:
                    print(f' - MSE increased: {mse}')
                    max_mse = mse

            end_time = now + end_time_offset

        else:
            if encoding and now > end_time:
                encoder.output.stop()
                encoding = False
                new_fname = os.path.join(outdir, f'{file_basename}_{max_mse:.1f}.h264')
                print(f'- Motion End : {new_fname}')
                # rename file to include max_mse
                os.rename(outfile, new_fname)
                # TODO: delete file if max_mse below threshold?

    prev = cur

picam2.stop_encoder()
