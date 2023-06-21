#!/usr/bin/env python3
import argparse
import glob
import os
import sys

import cv2
from datetime import datetime


def parse_args():
    parser = argparse.ArgumentParser('Make a directory full of images into a video')

    parser.add_argument('--fps', type=int,
                        help='Frames Per Second of video. (default: 24)',
                        default=24)
    parser.add_argument('--type', help='type of image file (extension: png, jpg, etc)')
    parser.add_argument('--output', help='name / path of output file: default: "output.mov"', default='output.mov')
    parser.add_argument('--darkframe', help='specify a "dark frame" to subract from each frame to '
                                            'eliminate "hot pixels"')
    parser.add_argument('imgdir', help='path to directory holding images')
    return parser.parse_args()

print(sys.argv)

config = parse_args()

IMAGE_DIR = config.imgdir

darkframe = None if config.darkframe is None else cv2.imread(config.darkframe)

if not os.path.isdir(IMAGE_DIR):
    print(f'image dir does not exist or is not a directory.')
    sys.exit(1)

filelist = glob.glob(os.path.join(IMAGE_DIR, f'*.{config.type}') )
filelist.sort()

if len(filelist) < 1:
    print(f'No files found in {IMAGE_DIR}')
    sys.exit(1)

img1 = cv2.imread(filelist[0])


height, width, _ = img1.shape
print(f'Image Size: {width} x {height}')
if darkframe is not None:
    dh, dw, _ = darkframe.shape
    if dh != height or dw != width:
        print(f'Dark frame size must match input images.')
        sys.exit(1)

img1 = None

# choose codec according to format needed
#fourcc = cv2.VideoWriter_fourcc(*'mp4v')
#fourcc = cv2.VideoWriter_fourcc(*'avc1')
#video = cv2.VideoWriter('video.avi', fourcc, 1, (width, height))


fps = config.fps

capSize = (width,height) # this is the size of my source video
fourcc = cv2.VideoWriter_fourcc('m', 'p', '4', 'v') # note the lower case
video = cv2.VideoWriter()
success = video.open(config.output,fourcc,fps,capSize,True)

start = datetime.now()
count = 0
total = len(filelist)

for file in filelist:
    img = cv2.imread(file)
    if img is None:
        print(f'Could not load {file}')
        continue
    if darkframe is not None:
        img = cv2.subtract(img, darkframe)
    video.write(img)

    count += 1
    now = datetime.now()
    elapsed = now - start
    if elapsed.total_seconds() > 30:
        start = now
        print(f'{count:5}/{total:5} ({count/total*100:.0f}%: {file}')

cv2.destroyAllWindows()
video.release()

print(f'video written to {config.output}')