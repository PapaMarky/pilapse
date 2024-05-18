#!/usr/bin/python3
import argparse
import os
import signal
import sys

import time
import math
from datetime import datetime, timedelta

import cv2
import numpy as np

from picamera2 import Picamera2, MappedArray
Picamera2.set_logging(Picamera2.WARNING)
os.environ['LIBCAMERA_LOG_LEVELS'] = 'ERROR'

from picamera2.encoders import H264Encoder, Quality
from picamera2.outputs import CircularOutput
import libcamera

from collections import deque

N = 1.5
class RingBuffer(object):
    """ class that implements a not-yet-full buffer """
    def __init__(self, size_max):
        self.max = size_max
        self.data = []
        self.cur = 0
        self._total = 0
        self.average = None
        self._is_full = False
        self._motion_detected = False

    @property
    def motion_detected(self):
        return self._motion_detected

    def append_full(self, x):
        """ Append an element overwriting the oldest one. """
        # If the new value is significantly bigger than the average, feed the average into the ring buffer so
        # that the average is not affected by the spikes.
        self._motion_detected = (x >= self.average * N)
        if self._motion_detected:
            x = self.average

        old_x = self.data[self.cur]
        self._total += x - old_x
        self.data[self.cur] = x
        self.cur = (self.cur+1) % self.max

    def append(self,x):
        """append an element at the end of the buffer"""
        if self._is_full:
            self.append_full(x)
        else:
            self.data.append(x)
            self._total += x
            if len(self.data) >= self.max:
                self._is_full = True

        self.average = self._total / len(self.data)
        return self.average


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

def get_program_name():
    name = os.path.basename(sys.argv[0])
    s = name.split('.')
    if s[-1] == 'py':
        name = '.'.join(s[:-1])
    return name


# h264 supported resolutions
'''
854 x 480 (16:9 480p)
1280 x 720 (16:9 720p)
1920 x 1080 (16:9 1080p)
640 x 480 (4:3 480p)
1280 x 1024 (5:4)
1920 x 1440 (4:3)
'''
width = 1920
height = 1080
GREEN = (0, 255, 0)
BLUE = (255, 0, 0)
RED = (0, 0, 255)
YELLOW = (0, 255, 255)
font = cv2.FONT_HERSHEY_SIMPLEX
scale = 1
thickness = 2

radius = 15
origin_red_dot = (width - radius * 2, radius * 2)
origin_blue_dot = (width - int(radius * 4.5), radius * 2)
origin_green_dot = (width - int(radius * 7), radius * 2)


parser = argparse.ArgumentParser('Simple video motion capture based on Picamera2')

### TODO : Implement "night mode".
# When it is dark (transition at lux 2.2 ... 2.0), set fps to 15, exposure to 66666.66, and ISO to 2200
# filenames should reflect correct FPS

parser.add_argument('--exposure', type=int,
                    help='force the exposure speed (Microseconds). If fps frequent, it will be reduced')
parser.add_argument('--fps', type=int, default=30,
                    help='output video frames per second. If this is too high for the requested exposure time, '
                         'fps will be reduced. Default: 30. Faster values impact the motion detection algorithm')
parser.add_argument('--seconds', type=float, help='Number of seconds in circular buffer (default: 5)', default=5.0)
parser.add_argument('--mse', type=float, default=7.0,
                    help='Sensitivity to motion (mean square error). If something like wind is triggering motion, '
                         'try setting this to a higher value. Actual values are logged to give you an idea of what '
                         'to set it to. If you make this value too low, noise will cause constant motion detection. '
                         'Default: 7.0')
parser.add_argument('--delta', type=float, default=0.1, help='Sensitivity')
parser.add_argument('--minmotion', type=float, default=0.5, help='Minumum time in seconds that motion must be '
                                                                 'contiguous to count')
parser.add_argument('--zoom', type=float, default=1.0,
                    help='Digital zoom value to apply to camera. Default 1.0 (no zoom)')
parser.add_argument('--flip', action='store_true',
                    help='Rotate image 180 degrees. Use this if your videos are upside down.')
parser.add_argument('--stop-at', type=str,
                    help='Stop running when this time is reached. (If this time has already passed today, '
                         'stop at this time tomorrow. Format: HH:MM:SS (24 hour clock)')
# Custom Exposure Helper:
# https://docs.google.com/spreadsheets/d/1cXzNoYFv1LZ3sZDgmQqybG2FHg8_APGk9uwHwIdpiM0/edit?usp=sharing
parser.add_argument('--custom', action='store_true', help='Use custom Exposure table')

parser.add_argument('--debug-discard', action='store_true', help='Debug discarding clips with short motions')
args = parser.parse_args()

print(f'ARGS: {args}')
debug = True


class MotionCamera(object):
    CURRENT_CAMERA = None

    def __init__(self, args):
        if self.CURRENT_CAMERA is not None:
            raise Exception('You can only have one camera at a time')

        self.args = args
        self.lsize = (320,240)
        self._size = (width, height) # sizes are constrained. See variable definitions
        self.exp = args.exposure
        self.fps = args.fps
        self.consecutive_frames = 0
        self.BUFFER_SIZE = math.ceil(args.seconds * self.fps)
        self.file_basename = ''
        self.TIME_TO_STOP = False
        self.stop_at = None
        if args.stop_at is not None:
            stop_time = args.stop_at.split(':')
            hour = int(stop_time[0])
            minute = int(stop_time[1])
            second = int(stop_time[2])

            now = datetime.now()
            self.stop_at = now.replace(hour=hour, minute=minute, second=second, microsecond=0)
            if self.stop_at < now:
                print(f'WARNING: {self.stop_at} is in the past. Assuming you mean tomorrow and adjusting...')
                self.stop_at += timedelta(days=1)
        self.delta = args.delta
        self.MAX_MSE = args.mse
        self.max_mse = 0
        self.total_frames = 0
        self.motion_frames = 0
        self.total_mse = 0
        self.mse = 0
        self.now = datetime.now()
        self.average = 0
        self.debug_discard = args.debug_discard
        self.cf_threshold = args.fps * args.minmotion
        self.minmotion = args.minmotion
        self.outdir = ''
        self.tempdir = '/home/pi/inbox'
        os.makedirs(self.tempdir, exist_ok=True)
        self.buffer = RingBuffer(self.BUFFER_SIZE * 9)

        self.picam2 = Picamera2()

        # Track the "fps" of the loop and the callback (add_mse) so we know when we have overburdoned the callback
        self.loop_previous_time = None
        self.loop_fps = 0
        self.callback_previous_time = None
        self.callback_fps = 0

    def setup(self):
        controls={
            'AeEnable': True,
            'AwbEnable': True,
            'NoiseReductionMode': libcamera.controls.draft.NoiseReductionModeEnum.HighQuality,
        }
        if args.custom:
            controls['AeExposureMode'] = libcamera.controls.AeExposureModeEnum.Custom

        if args.exposure is not None:
            maxfps = self.exp / 1000000
            if self.fps > maxfps:
                print(f'WARNING: fps is too fast. Setting to {maxfps:.4f}')
                fps = maxfps
            controls["FrameDurationLimits"] = (self.exp, self.exp)
            controls["ExposureTime"] = self.exp
        else:
            controls["FrameRate"] = self.fps
            # might be good at night?

        video_config = self.picam2.create_video_configuration(
            main={"size": self._size, "format": "RGB888"},
            lores={"size": self.lsize, "format": "YUV420"},
            controls=controls,


        )
        video_config['transform'] = libcamera.Transform(hflip=args.flip, vflip=args.flip)
        self.picam2.configure(video_config)

        self.set_outdir()

    def start(self):
        self.picam2.start_preview()
        self.encoder = H264Encoder(10000000, repeat=True)
        # 5 seconds X FramesPerSecond
        print(f'BUFFER_SIZE = {self.BUFFER_SIZE} (fps: {self.fps}, seconds: {args.seconds}) MSE Threshold: {self.MAX_MSE}')
        self.encoder.output = CircularOutput(buffersize=self.BUFFER_SIZE)
        # picam2.encoder = encoder
        print(f'encoder: {self.encoder}')

        def add_mse(request):
            # Calculate the "fps" of this callback
            now = datetime.now()
            if self.callback_previous_time is not None:
                elapsed = now - self.callback_previous_time
                self.callback_fps = 1.0/elapsed.total_seconds()
            self.callback_previous_time = now

            left = 30
            ystep = 60
            y = ystep
            with MappedArray(request, "main") as m:
                metadata = request.get_metadata()
                lux = metadata['Lux'] if 'Lux' in metadata else 'NOLUX'
                exp_time = metadata['ExposureTime'] if 'ExposureTime' in metadata else 'NOEXP'
                gain = metadata['AnalogueGain']
                ts = datetime.strftime(now, '%Y/%m/%d %H:%M:%S')
                cv2.putText(m.array, ts, (left, y), font, scale, (0,0,0), thickness + 2)
                cv2.putText(m.array, ts, (left, y), font, scale, GREEN, thickness)
                message = f'ISO: {gain * 100:.0f} SS: {int(exp_time)} LUX: {lux:.02f} FPS: {self.fps:.1f} (loop: {int(self.loop_fps)} cb: {int(self.callback_fps)})'
                text_color = GREEN
                y += ystep
                cv2.putText(m.array, message, (left, y), font, scale, (0,0,0), thickness + 2)
                cv2.putText(m.array, message, (left, y), font, scale, text_color, thickness)

                # DISPLAY THESE VALUES:
                #
                # per frame values
                # Frame MSE
                #
                # per clip values
                # Max MSE
                # Total Frames (of motion)
                # Consecutive Frames (of motion)
                # Average Motion (average mse of motion frames
                #
                if False:
                    ### Doing all of this slows the outer loop down too much.
                    ### Consider retrying file with per-frame data?
                    blue_motion = self.mse - self.average > self.delta # THIS NEEDS TO FACTOR INTO CLIP DISCARD
                    XN = self.mse / self.average if self.average > 0 else 0.0
                    percent = self.motion_frames / self.total_frames * 100.0 if self.total_frames > 0 else 0
                    am = self.total_mse / self.motion_frames if self.motion_frames > 0 else 0
                    message = f'M: {self.mse:3.2f} A: {self.average:3.4f} d: {self.mse - self.average:8.4f} ' \
                              f'({XN:6.1f} - {self.delta}) CF: {self.consecutive_frames} X: {self.max_mse:5.1f} ' \
                              f't:{self.total_frames:4} m:{self.motion_frames:4} {percent:.0f}% AM: {am:6.2f}'
                    text_color = GREEN if blue_motion else YELLOW
                    y = height - ystep
                    cv2.putText(m.array, message, (left, y), font, scale, (0,0,0), thickness + 2)
                    cv2.putText(m.array, message, (left, y), font, scale, text_color, thickness)
                    if self.mse >= self.MAX_MSE:
                        cv2.circle(m.array, origin_red_dot, radius, RED, -1)
                    if blue_motion:
                        cv2.circle(m.array, origin_blue_dot, radius, BLUE, -1)
                    if self.buffer is not None and self.buffer.motion_detected:
                        cv2.circle(m.array, origin_green_dot, radius, GREEN, -1)

        self.picam2.post_callback = add_mse
        self.picam2.start()
        self.picam2.start_encoder(self.encoder, quality=Quality.VERY_HIGH)
        metadata = self.picam2.capture_metadata()
        print(f'METADATA: {metadata}')

        if args.zoom > 1.0:
            original_scaler_crop = metadata['ScalerCrop']
            zoom = args.zoom
            print(f'Setting Zoom to {zoom}')
            x, y, w, h = original_scaler_crop
            new_w = w/zoom
            new_h = h/zoom
            new_x = x + w/2 - new_w/2
            new_y = y + h/2 - new_h/2
            self.picam2.set_controls({
                'ScalerCrop': (int(new_x), int(new_y), int(new_w), int(new_h))
            })
            time.sleep(1.0)
            print(f'Zoomed ScalerCrop: {self.picam2.capture_metadata()["ScalerCrop"]}')

    def run(self):
        print('- BEGINNING MOTION DETECTION AND CAPTURE -')
        if self.stop_at is not None:
            print(f'Timelapse will run until {self.stop_at.strftime("%Y-%m-%d %H:%M:%S")} '
                  f'(Time from now: {timedelta_formatter(self.stop_at - datetime.now())})')

        cframes = 0

        outfile = ''
        prev = None
        encoding = False
        end_time = None
        end_time_offset = timedelta(seconds=self.args.seconds)
        while True:
            ### NOTE If we try to do too much in add_mse callback, this loop falls behind
            if self.TIME_TO_STOP:
                print('Shutting down...')
                break
            cur = self.picam2.capture_buffer("lores")
            w, h = self.lsize
            cur = cur[:w * h].reshape(h, w)
            # TODO : define area of interest (top, bottom, left, right) and crop each frame
            #  then compare just the "cropped" parts
            # EX: cropped_image = img[Y:Y+H, X:X+W]
            # Optionally use post_callback to add rectangle on output in the setup tool

            # Create an overlay with the MSE for debugging
            if prev is not None:
                self.now = datetime.now()
                ## Calculate FPS of "loop" so we can compare to expected fps and fps of callback
                ## This lets us know if the callback is doing too much
                if self.loop_previous_time is not None:
                    elapsed = self.now - self.loop_previous_time
                    self.loop_fps = 1.0 / elapsed.total_seconds()
                self.loop_previous_time = self.now
                if self.now.day != self.outdir_day:
                    self.set_outdir()

                if self.stop_at is not None and self.now >= self.stop_at:
                    print(f'Stop time {self.stop_at} reached...')
                    break
                # Measure pixels differences between current and
                # previous frame
                self.mse = np.square(np.subtract(cur, prev)).mean()
                self.average = self.buffer.append(self.mse)
                current_delta = self.mse - self.average
                self.total_frames += 1
                # compare the average to the mse. If self.mse is N above average, motion detected
                # blue_motion = self.mse - self.average > self.delta
                if (self.mse - self.average > self.delta) or (current_delta > self.delta) or self.buffer.motion_detected:
                    if not encoding:
                        self.max_mse = self.mse
                        self.total_frames = 0
                        self.total_mse += self.mse
                        file_basename = f"{self.now.strftime('%Y%m%d-%H%M%S')}_motion_{self.mse:.1f}"
                        outfile = os.path.join(self.tempdir, f"{file_basename}-{self.fps}fps.h264")
                        self.encoder.output.fileoutput = outfile
                        self.encoder.output.start()
                        encoding = True
                        end_time = self.now + end_time_offset
                        print(f'Motion Detected: {outfile}, mse: {self.mse}')
                    else:
                        self.total_mse += self.mse
                        if self.mse > self.max_mse:
                            print(f' - MSE increased: {self.mse:.4f} delta: {current_delta:.4f} m: {(cframes + 1)/args.fps}')
                            self.max_mse = self.mse
                    cframes += 1
                    self.motion_frames += 1
                    if cframes > self.consecutive_frames:
                        self.consecutive_frames = cframes
                    if self.consecutive_frames >= self.cf_threshold:
                        end_time = self.now + end_time_offset

                else:
                    cframes = 0
                    if encoding and self.now > end_time:
                        self.encoder.output.stop()
                        encoding = False
                        new_fname = ''
                        discarding = ''
                        am = self.total_mse / self.motion_frames if self.motion_frames > 0 else 100
                        # self.buffer.motion_detected is per frame, not per clip. Can we use it?
                        discard = ((self.consecutive_frames < self.cf_threshold) or (am < 0.9))
                        self.motion_frames = 0
                        if discard:
                            seconds = (1.0/args.fps) * self.consecutive_frames
                            print(f'   - Less than {self.minmotion} seconds of motion ({seconds:.2f}). Discarding clip. CF: {self.consecutive_frames} (T: {self.cf_threshold} AM: {am}')
                            discarding = 'discards'
                            if not self.debug_discard:
                                os.remove(outfile)
                        if not discard or self.debug_discard:
                            d = f''
                            if discard:
                                d = f'-{self.consecutive_frames}-{am:.2f}'
                            new_fname = os.path.join(self.outdir, discarding, f'{file_basename}_{self.max_mse:.1f}{d}-{self.fps}fps.h264')
                            os.rename(outfile, new_fname)
                        print(f'- Motion End : {new_fname} (CF: {self.consecutive_frames}/{self.cf_threshold:.2f})')
                        self.consecutive_frames = 0
                        self.total_mse = 0
                        self.total_frames = 0
                        # rename file to include max_mse
                        # TODO: delete file if max_mse below threshold?

            prev = cur
        self.picam2.stop_encoder()

    def set_outdir(self):
        now = datetime.now()
        self.outdir = now.strftime('/home/pi/exposures/%Y%m%d-motion2')
        os.makedirs(self.outdir, exist_ok=True)
        if self.debug_discard:
            os.makedirs(os.path.join(self.outdir, 'discards'), exist_ok=True)
        self.outdir_day = now.day
    def stop(self):
        self.TIME_TO_STOP = True



camera = MotionCamera(args)

def exit_gracefully(signum, frame):
    print(f'\n{get_program_name()} SHUTTING DOWN due to {signal.Signals(signum).name}')
    camera.stop()

signal.signal(signal.SIGINT, exit_gracefully)
signal.signal(signal.SIGTERM, exit_gracefully)

camera.setup()
camera.start()
camera.run()
