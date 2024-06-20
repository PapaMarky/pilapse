#!/usr/bin/env python3
import argparse
import sys
from datetime import datetime, timedelta
import time
import subprocess


now = datetime.now()


parser = argparse.ArgumentParser('Auto Pull frames / clips from PiCam')
parser.add_argument('--timelapse', action='store_true', help='Pull timelapse frames')
parser.add_argument('host')

args = parser.parse_args()
HOST=args.host

print(f'### Starting Auto pull from {HOST} at {now}')

def run(cmd):
    print(f' - RUN {cmd}')
    p = subprocess.run(cmd.split())
    if p.returncode != 0:
        print(f'# - ERROR RUNNING {cmd}')
    print(p.stdout)
            

while True:
    pull_command = f'./pull-from.sh {HOST}'
    run(pull_command)

    if not args.timelapse:
        now2 = datetime.now()
        if now.hour != now2.hour:
            print('### Get last of yesterday')
            # h264_cmd = f'python3 /Users/mark/git/pilapse/h264_to_mov.py {HOST}/{now.strftime("%Y%m%d")}-motion2/ --all --delete'
            h264_cmd = f'python3 /Users/mark/git/pilapse/pc2-motion-post.py {HOST}/{now.strftime("%Y%m%d")}-motion2'
            run(h264_cmd)
            now = now2
        # h264_cmd = f'python3 /Users/mark/git/pilapse/h264_to_mov.py {HOST}/{now.strftime("%Y%m%d")}-motion2/ --all --delete'
        h264_cmd = f'python3 /Users/mark/git/pilapse/pc2-motion-post.py {HOST}/{now.strftime("%Y%m%d")}-motion2'
        run(h264_cmd)
    seconds_pause = 1 * 60
    print(f'Restart in {seconds_pause/60:.1f} minutes (at {datetime.now() + timedelta(seconds=seconds_pause)})')
    time.sleep(seconds_pause) # check every 5 minutes
