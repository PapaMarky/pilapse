import argparse
import re
from datetime import datetime
from datetime import timedelta
import glob

import cv2
import os

parser = argparse.ArgumentParser('Convert h264 format video to mp4')
parser.add_argument('--fps', type=float, help='FPS of h264 video')
parser.add_argument('--delete', action='store_true', help='If set, delete the h264 file')
parser.add_argument('--all', action='store_true',
                    help='Treat "video_in" as a directory and convert all h264 files found')
parser.add_argument('--intype', '-I', type=str, default='h264',
                    help='Type of input video. Default: h264')
parser.add_argument('--outtype', '-O', type=str, default='mp4',
                    help='extension of output file. Default: "mp4". Video format will be mp4')
parser.add_argument('video_in', type=str, help='Path to video file to convert')
config = parser.parse_args()

def convert_file(video_in, outtype):
    outfile = os.path.splitext(video_in)[0] + f'.{outtype}'
    print(f'converting: {video_in}')
    print(f'    output: {outfile}')

    if config.fps is None:
        print(f'FPS not specified, checking filename')
        m = re.match(r'.*-([\d\.]+)fps\..*', video_in)
        if m:
            config.fps = float(m.group(1))
            print(f'FPS detected in filename: {config.fps}')


    video_cap = cv2.VideoCapture(video_in)
    frame_width = int(video_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(video_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(video_cap.get(cv2.CAP_PROP_FPS)) if config.fps is None else config.fps
    print(f' - Frame rate: {fps} FPS')
    print(f' - Frame size: {frame_width} x {frame_height}')
    capSize = (frame_width, frame_height) # this is the size of my source video
    fourcc = cv2.VideoWriter_fourcc('m', 'p', '4', 'v') # note the lower case
    video = cv2.VideoWriter()
    video.open(outfile,fourcc,fps,capSize)

    frame_count = 0
    while True:
        # `success` is a boolean and `frame` contains the next video frame
        success, frame = video_cap.read()
        if not success:
            break
        video.write(frame)
        frame_count += 1

    # we also need to close the video and destroy all Windows
    video_cap.release()
    video.release()

    print(f' - Done: {outfile}')
    if config.delete:
        print(f'   - deleting {video_in}')
        os.remove(video_in)
    return frame_count

video_in = config.video_in

def timedelta_formatter(td:timedelta):
    #  TODO : move to library
    td_sec = td.seconds
    hour_count, rem = divmod(td_sec, 3600)
    minute_count, second_count = divmod(rem, 60)
    msg = f'{hour_count:02}:{minute_count:02}:{second_count:02}'
    if td.days > 0:
        day_str = f'{td.days} day'
        if td.days > 1:
            day_str += 's'
        day_str += ' '
        msg = day_str + msg
    return msg

if __name__ == '__main__':
    video_list = []
    if config.all:
        glob_path = video_in + f'/*.{config.intype}'
        video_list = glob.glob(glob_path)
        discard_in = os.path.join(video_in, 'discards')
        if os.path.exists(discard_in):
            print(f'Adding files in {discard_in}')
            glob_path = discard_in + f'/*.{config.intype}'
            video_list += glob.glob(glob_path)

        video_list.sort()
    else:
        video_list.append(config.video_in)

    start_time = datetime.now()
    frame_count = 0
    file_count = 0
    total_files = len(video_list)

    def progress_str():
        if file_count < total_files:
            return f'{file_count + 1} of {total_files}'
        else:
            return f'FINISHED'
    print(f'----- {progress_str()} -----')
    for video in video_list:
        file_start_time = datetime.now()
        nframes = convert_file(video, config.outtype)
        frame_count += nframes
        file_elapsed = datetime.now() - file_start_time
        file_count += 1
        print(f'Elapsed Time: {timedelta_formatter(file_elapsed)}')
        print(f' - frames: {nframes}')
        print(f' - frames per second: {(nframes / file_elapsed.total_seconds()):.2f}')
        print(f'----- {progress_str()} -----')
    elapsed = datetime.now() - start_time
    print(f'Total Elapsed Time: {timedelta_formatter(elapsed)}')
    print(f'Total Files: {file_count}')
    if file_count > 0:
        print(f'Per File Averages: elapsed time: {timedelta_formatter(elapsed/file_count)}, '
              f'frames: {nframes/file_count:.2f}, fps: {(nframes/elapsed.total_seconds())/file_count:.2f}')
    else:
        print(f'No files found')