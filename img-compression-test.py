#!/usr/bin/env python3
import datetime
import os.path

import cv2
import sys

if len(sys.argv) < 2:
    print(f'Usage: {sys.argv[0]} <IMAGEFILE>')
    sys.exit(1)

file_in = sys.argv[1]

if not os.path.exists(file_in):
    print(f'Image file does not exist: {file_in}')

MEG = 1024 * 1024

def size_str(i):
    return f'{i / MEG:.2f} M'

img = cv2.imread(file_in)
print(f'Test compression using {file_in}')
print(f'{file_in:11} | {size_str(os.path.getsize(file_in)):8} | ')
print('---------')
for i in range(0,10):
    out_file = f'test_{i}.png'
    start_time = datetime.datetime.now()
    cv2.imwrite(out_file, img, [cv2.IMWRITE_PNG_COMPRESSION, i])
    elapsed = datetime.datetime.now() - start_time
    s = os.path.getsize(out_file)
    print(f'{out_file:11} | {size_str(s):8} | {elapsed}')
