#!/usr/bin/env python3
import argparse
import glob
import os
import sys

import cv2
from datetime import datetime

from pilapse.darkframe import apply_darkframe, get_contours

def parse_args():
    parser = argparse.ArgumentParser('Make a directory full of images into a video')

    parser.add_argument('--fps', type=int,
                        help='Frames Per Second of video. (default: 24)',
                        default=24)
    parser.add_argument('--type', help='type of image file (extension: png, jpg, etc)')
    parser.add_argument('--output', help='name / path of output file: default: "output.mov"', default='output.mov')
    parser.add_argument('imgdir', help='path to directory holding images')
    parser.add_argument('--skip', type=int, default=0,
                        help='Number of frames to skip. Default is zero. Zero frames are skipped, so all frames are '
                             'used. If set to 1, everyother frame is used; if set to 2, every 3rd frame is used; etc.')
    darkgroup = parser.add_argument_group('Using Darkframe to clean up dead / hot pixels')
    darkgroup.add_argument('--darkframe', help='specify a "dark frame" to subract from each frame to '
                                            'eliminate "hot pixels"')
    darkgroup.add_argument('--threshold', '-t', type=int, default=7,
                        help='Threshold determines how large of a defect to try to fix')

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
dark_contours = None
if darkframe is not None:
    dh, dw, _ = darkframe.shape
    if dh != height or dw != width:
        print(f'Dark frame size must match input images.')
        sys.exit(1)
    dark_contours, _ = get_contours(darkframe, threshold=config.threshold)

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

skipped = 0
for file in filelist:
    if skipped < config.skip:
        skipped += 1
        count += 1
        continue
    skipped = 0
    img = cv2.imread(file)
    if img is None:
        print(f'Could not load {file}')
        continue
    if darkframe is not None:
        img = apply_darkframe(img, dark_contours)
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