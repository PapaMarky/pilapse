import argparse

import cv2
import sys
import os

parser = argparse.ArgumentParser('Convert h264 format video to mp4')
parser.add_argument('video_in', type=str, help='Path to video file to convert')
config = parser.parse_args()

video_in = config.video_in

outfile = os.path.splitext(video_in)[0] + '.mp4'
print(f'converting: {video_in}')
print(f'output: {outfile}')

video_cap = cv2.VideoCapture(video_in)
frame_width = int(video_cap.get(cv2.CAP_PROP_FRAME_WIDTH))
frame_height = int(video_cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
fps = int(video_cap.get(cv2.CAP_PROP_FPS))
print("Frame rate: ", int(fps), "FPS")
print(f'Frame size: {frame_width} x {frame_height}')
capSize = (frame_width,frame_height) # this is the size of my source video
fourcc = cv2.VideoWriter_fourcc('m', 'p', '4', 'v') # note the lower case
video = cv2.VideoWriter()
success = video.open(outfile,fourcc,fps,capSize)

n = 1
while True:
    # `success` is a boolean and `frame` contains the next video frame
    n += 1
    success, frame = video_cap.read()
    pos = video_cap.get(cv2.CAP_PROP_POS_FRAMES)
    if not success:
        print(f'Success not true')
        break
    # cv2.imshow("frame", frame)
    video.write(frame)
    # wait 20 milliseconds between frames and break the loop if the `q` key is pressed
    # if cv2.waitKey(200) == ord('q'):
    #    break

# we also need to close the video and destroy all Windows
video_cap.release()
video.release()

print(f'Done: {outfile}')