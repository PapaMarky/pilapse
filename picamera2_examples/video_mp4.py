#!/usr/bin/python3
import time

from picamera2 import Picamera2
from picamera2.encoders import H264Encoder
from picamera2.outputs import FfmpegOutput
import libcamera

picam2 = Picamera2()
video_config = picam2.create_video_configuration()
video_config['transform'] = libcamera.Transform(hflip=1, vflip=1)
picam2.configure(video_config)

encoder = H264Encoder(10000000, framerate=)
output = FfmpegOutput('test.mp4')

picam2.start_recording(encoder, output)
time.sleep(10)
picam2.stop_recording()
