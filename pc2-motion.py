#!/usr/bin/python3
import os
# TODO: set "stop time" forward each time motion detected
# TODO: incorporate mpeg encoder

import time
from datetime import datetime, timedelta

import numpy as np

from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import CircularOutput
import libcamera

lsize = (320, 240)
picam2 = Picamera2()
#video_config = picam2.create_video_configuration(main={"size": (1280, 720), "format": "RGB888"}, lores={
#    "size": lsize, "format": "YUV420"})
video_config = picam2.create_video_configuration(main={"size": (1929, 1088), "format": "RGB888"}, lores={
    "size": lsize, "format": "YUV420"})
video_config['transform'] = libcamera.Transform(hflip=1, vflip=1)
picam2.configure(video_config)
picam2.start_preview()
encoder = H264Encoder(10000000, repeat=True)
encoder.output = CircularOutput()
picam2.encoder = encoder
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
while True:
    cur = picam2.capture_buffer("lores")
    cur = cur[:w * h].reshape(h, w)
    # TODO : define area of interest (top, bottom, left, right) and crop each frame
    #  then compare just the "cropped" parts
    # EX: cropped_image = img[Y:Y+H, X:X+W]
    # Optionally use post_callback to add rectangle on output in the setup tool
    if prev is not None:
        now = datetime.now()
        # Measure pixels differences between current and
        # previous frame
        mse = np.square(np.subtract(cur, prev)).mean()
        if mse > 7:
            if not encoding:
                # if we start recording immediately we get a 5 second lead. consider waiting 2 seconds.
                epoch = int(time.time())
                outfile = os.path.join(outdir, f"{now.strftime('%Y%m%d-%H%M%S.%f')}_motion.h264")
                encoder.output.fileoutput = outfile
                encoder.output.start()
                encoding = True
                print(f'Motion Detected: {outfile}, mse: {mse}')
            end_time = now + end_time_offset

        else:
            if encoding and now > end_time:
                encoder.output.stop()
                encoding = False
                print('- Motion End -')
    prev = cur

picam2.stop_encoder()