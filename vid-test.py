import time

import cv2
import sys
import os
from picamera import PiCamera

testfile = 'test_vid.h264'
outfile = 'test_vid_out.mov'
print(f'creating: {testfile}')

camera = PiCamera(sensor_mode=5,
                  # framerate_range=(1/10, 40),
                  resolution=(640,480))
camera.start_recording(testfile, format=None)

time.sleep(3)
camera.stop_recording()

video_cap = cv2.VideoCapture(testfile)
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
    print(f'show frame {n}...')
    n += 1
    success, frame = video_cap.read()
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
#cv2.destroyAllWindows()
