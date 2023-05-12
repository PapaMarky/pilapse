#!/usr/bin/env python3
import glob
import os
import sys

import cv2
from datetime import datetime

print(sys.argv)

if len(sys.argv) < 2:
    print(f'USAGE: {sys.argv[0]} DIRECTORY_PATH')
    sys.exit(1)

IMAGE_DIR = sys.argv[1]

if not os.path.isdir(IMAGE_DIR):
    print(f'image dir does not exist or is not a directory.')
    sys.exit(1)

filelist = glob.glob(os.path.join(IMAGE_DIR, '*.png') )
filelist.sort()

if len(filelist) < 1:
    print(f'No files found in {IMAGE_DIR}')
    sys.exit(1)

img1 = cv2.imread(filelist[0])


height, width, _ = img1.shape
print(f'Image Size: {width} x {height}')
img1 = None

# choose codec according to format needed
#fourcc = cv2.VideoWriter_fourcc(*'mp4v')
#fourcc = cv2.VideoWriter_fourcc(*'avc1')
#video = cv2.VideoWriter('video.avi', fourcc, 1, (width, height))


fps = 24
capSize = (width,height) # this is the size of my source video
fourcc = cv2.VideoWriter_fourcc('m', 'p', '4', 'v') # note the lower case
video = cv2.VideoWriter()
success = video.open('output.mov',fourcc,fps,capSize,True)

start = datetime.now()
count = 0
total = len(filelist)

for file in filelist:
    img = cv2.imread(file)
    if img is None:
        print(f'Could not load {file}')
        continue
    video.write(img)

    count += 1
    now = datetime.now()
    elapsed = now - start
    if elapsed.total_seconds() > 30:
        start = now
        print(f'{count:5}/{total:5} ({count/total*100:.0f}%: {file}')

cv2.destroyAllWindows()
video.release()