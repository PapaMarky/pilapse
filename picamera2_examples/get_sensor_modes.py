#!/usr/bin/python3
import os

import picamera2 as pc2
from picamera2 import Picamera2
Picamera2.set_logging(Picamera2.WARNING)
os.environ['LIBCAMERA_LOG_LEVELS'] = 'ERROR'

c = pc2.Picamera2()

mlist = []
n = 0

modes = c.sensor_modes

cinfo = c.global_camera_info()
print('')
print(f'Model: {cinfo[0]["Model"]}')

print(f' # | {"size":10} | {"exp. limits":15} | {"crop limits":23} |')
print(f'{"-"*3}|{"-"*12}|{"-"*17}|{"-"*25}|')
for mode in modes:
    size = f'{mode["size"][0]}x{mode["size"][1]}'
    el = mode['exposure_limits']
    elimits = f'{el[0]:3} - {el[1]:9}'
    cl = mode['crop_limits']
    crop_limits = f'{cl[0]:5} {cl[1]:5} {cl[2]:5} {cl[3]:5}'
    print(f'{n:2} | {size:10} | {elimits} | {crop_limits} |')
    n += 1
