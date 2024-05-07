#!/usr/bin/python3
import argparse
import os
import sys

import picamera2 as pc2
from picamera2 import Picamera2
from libcamera import controls

Picamera2.set_logging(Picamera2.WARNING)
os.environ['LIBCAMERA_LOG_LEVELS'] = 'ERROR'

parser = argparse.ArgumentParser('Create table of sensor modes')
parser.add_argument('--html', action='store_true',
                    help='Create an html table (default format is ascii / Markdown)')
args = parser.parse_args()
c = pc2.Picamera2()

cinfo = c.global_camera_info()
modes = c.sensor_modes

def generate_ascii_table(modes, model):
    n = 0
    print('')
    print(f'# Camera Model: {model}')

    print(f'| # | {"Size":10} | {"Exposure Limits":20} | {"Crop Limits":23} |')
    print(f'|{"-"*3}|{"-"*12}|{"-"*22}|{"-"*25}|')
    for mode in modes:
        size = f'{mode["size"][0]}x{mode["size"][1]}'
        el = mode['exposure_limits']
        elimits = f'{el[0]:8} - {el[1]}'
        cl = mode['crop_limits']
        crop_limits = f'{cl[0]:5} {cl[1]:5} {cl[2]:5} {cl[3]:5}'
        print(f'|{n:2} | {size:10} | {elimits} | {crop_limits} |')
        crop_limits = f'{" ":5} {" ":5} {" ":5} {" ":5}'
        e1 = int(el[0])/1000000
        el2_1 = el[1]
        if isinstance(el2_1, float):
            el2_1 = int(el2_1) / 1000000
        else:
            el2_1 = '???'
        elimits2 = f'{e1:4.6f} - {el2_1}'
        print(f'|   | {" ":10} | {elimits2} | {crop_limits} |')

        n += 1
def generate_html_table(modes, model):
    print(f'<h2>Camera Model: {model}</h2>')
    print('<table>')
    print('<tr><th>#</th><th>Size</th><th colspan=2>Exposure Limits</th><th colspan=4>Crop Limits</th></tr>')
    n = 0
    for mode in modes:
        print('<tr>')
        print(f'<td rowspan=2>{n}</td>')
        print(f'<td rowspan=2>{mode["size"][0]} x {mode["size"][1]}</td>')
        el = mode['exposure_limits']
        e1 = int(el[0])/1000000
        e2 = int(el[1])/1000000
        print(f'<td>{el[0]}</td><td>{el[1]}</td>')
        cl = mode['crop_limits']
        print(f'<td rowspan=2>{cl[0]}</td><td rowspan=2>{cl[1]}</td><td rowspan=2>{cl[2]}</td><td rowspan=2>{cl[3]}</td>')
        print(f'')
        print('</tr>')
        print(f'<tr><td>{e1:.6f}</td><td>{e2:.2f}</td></tr>')
        n += 1
    print('</table>')

if args.html:
    generate_html_table(modes, cinfo[0]["Model"])
else:
    generate_ascii_table(modes, cinfo[0]["Model"])

def control_string(camera, control, enum=None):
    label = f'{control:>20}'
    if control in camera.camera_controls:
        c = camera.camera_controls[control]
        if enum:
            return f'{label}: Min: {enum(c[0])}, Max: {enum(c[1])}, Default: {enum(c[2])}'
        if isinstance(c, tuple) and len(c) == 3:
            return f'{label}: Min: {str(c[0])}, Max: {c[1]}, Def: {c[2]}'
        return f'{label}: c'
    return f'{label}: Not Available'

def control_row_data(camera, control, enum):
    if control in camera.camera_controls:
        c = camera.camera_controls[control]
        if enum is not None:
            return (control, enum(c[0]), enum(c[1]), enum(c[2]))
        if isinstance(c, tuple) and len(c) == 3:
            return (control, c[0], c[1], c[2])
        return (control, c)
    return (control, 'Not Available')
c.start()

control_list = (
    {'name': 'AfMode', 'enum': controls.AfModeEnum},
    {'name': 'LensPosition', 'enum': None},
    {'name': 'AeEnable', 'enum': None},
    {'name': 'AeExposureMode', 'enum': controls.AeExposureModeEnum},
    {'name': 'AeConstraintMode', 'enum': controls.AeConstraintModeEnum},
    {'name': 'AwbEnable', 'enum': None},
    {'name': 'AwbMode', 'enum': controls.AwbModeEnum},
    {'name': 'AnalogueGain', 'enum': None}
)

if args.html:
    print('<h2>Camera Controls</h2></br>')
    print('<table>')
    print('<tr><th>Control</th><th>Min</th><th>Max</th><th>Default</th></tr>')
else:
    print('\n# Camera Controls')
    print(f'| {"Control":16} | {"Min":30} | {"Max":30} | {"Default":30} |')
    print(f'|-{"-"*16}-|-{"-"*30}-|-{"-"*30}-|-{"-"*30}-|')

for control in control_list:
    data = control_row_data(c, control["name"], control["enum"])
    if len(data) == 4:
        if args.html:
            print(f'<tr><td>{data[0]}</td><td>{data[1]}</td><td>{data[2]}</td><td>{data[3]}</td></tr>')
        else:
            print(f'| {data[0]:16} | {str(data[1]):30} | {str(data[2]):30} | {str(data[3]):30} |')
    elif len(data) == 2:
        if args.html:
            print(f'<tr><td>{data[0]}</td><td colspan="3">{data[1]}</td></tr>')
        else:
            print(f'| {data[0]:16} | {data[1]:30} | {" ":30} | {" ":30} |')
    else:
        print(f'BAD DATA: len: {len(data)}, data: {data}')

c.stop()

if args.html:
    print('</table>')
else:
    print(f'|-{"-"*16}-|-{"-"*30}-|-{"-"*30}-|-{"-"*30}-|')
