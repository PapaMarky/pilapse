#!/usr/bin/python3
import os
# TODO: set "stop time" forward each time motion detected
# TODO: incorporate mpeg encoder

import time
from datetime import datetime, timedelta

import cv2
import numpy as np

from picamera2 import Picamera2, MappedArray
from picamera2.encoders import H264Encoder
from picamera2.outputs import CircularOutput
import libcamera

mse = 0
colour = (0, 255, 0)
origin = (0, 60)
font = cv2.FONT_HERSHEY_SIMPLEX
scale = 1
thickness = 2

debug = True
def add_mse(request):
    with MappedArray(request, "main") as m:
        cv2.putText(m.array, f'{mse:.2f}', origin, font, scale, colour, thickness)

lsize = (320, 240)
picam2 = Picamera2()
#video_config = picam2.create_video_configuration(main={"size": (1280, 720), "format": "RGB888"}, lores={
#    "size": lsize, "format": "YUV420"})
video_config = picam2.create_video_configuration(main={"size": (1920, 1080), "format": "RGB888"}, lores={
    "size": lsize, "format": "YUV420"})
video_config['transform'] = libcamera.Transform(hflip=0, vflip=0)
picam2.configure(video_config)
picam2.start_preview()
encoder = H264Encoder(10000000, repeat=True)
encoder.output = CircularOutput()
picam2.encoder = encoder
picam2.post_callback = add_mse
picam2.start()
picam2.start_encoder()

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

while True:
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
        if mse > 7:
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