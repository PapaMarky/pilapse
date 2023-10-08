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

from picamera2.encoders import H264Encoder
from picamera2.outputs import CircularOutput
import libcamera

from collections import deque


class RingBuffer(object):
    """ class that implements a not-yet-full buffer """
    def __init__(self, size_max):
        self.max = size_max
        self.data = []
        self.cur = 0
        self._total = 0
        self.average = None
        self._is_full = False

    def append_full(self, x):
        """ Append an element overwriting the oldest one. """
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

width = 1920
height = 1080
GREEN = (0, 255, 0)
BLUE = (255, 0, 0)
RED = (0, 0, 255)
YELLOW = (0, 255, 255)
top_origin_1 = (30, 60)
top_origin_2 = (30, 120)
font = cv2.FONT_HERSHEY_SIMPLEX
scale = 1
thickness = 2

radius = 15
origin_red_dot = (width - radius * 2, radius * 2)
origin_blue_dot = (width - int(radius * 4.5), radius * 2)


parser = argparse.ArgumentParser('Simple video motion capture based on Picamera2')
parser.add_argument('--exposure', type=int,
                    help='force the exposure speed (Microseconds). If fps frequent, it will be reduced')
parser.add_argument('--fps', type=float, default=30,
                    help='output video frames per second. If this is too high for the requested exposure time, '
                         'fps will be reduced. Default: 30.')
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
parser.add_argument('--custom', action='store_true', help='Use custom Exposure table')
parser.add_argument('--debug-discard', action='store_true', help='Debug discarding clips with short motions')
args = parser.parse_args()

debug = True


class MotionCamera(object):
    CURRENT_CAMERA = None

    def __init__(self, args):
        if self.CURRENT_CAMERA is not None:
            raise Exception('You can only have one camera at a time')

        self.args = args
        self.lsize = (320,240)
        self._size = (1920, 1080)
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
                self.top_at += timedelta(days=1)
        self.delta = args.delta
        self.MAX_MSE = args.mse
        self.mse = 0
        self.now = datetime.now()
        self.average = 0
        self.debug_discard = args.debug_discard
        self.cf_threshold = args.fps * args.minmotion
        self.minmotion = args.minmotion
        self.outdir = ''
        self.tempdir = '/home/pi/inbox'
        os.makedirs(self.tempdir, exist_ok=True)


        self.picam2 = Picamera2()

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
            if False:
                controls["ExposureTime"] = int(self.fps * 1000000)
                # might be good at night?
        video_config = self.picam2.create_video_configuration(
            main={"size": self._size, "format": "RGB888"},
            lores={"size": self.lsize, "format": "YUV420"},
            controls=controls
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
            with MappedArray(request, "main") as m:
                metadata = request.get_metadata()
                lux = metadata['Lux'] if 'Lux' in metadata else 'NOLUX'
                exp_time = metadata['ExposureTime'] if 'ExposureTime' in metadata else 'NOEXP'
                gain = metadata['AnalogueGain']
                blue_motion = self.mse - self.average > self.delta
                ts = datetime.strftime(self.now, '%Y/%m/%d %H:%M:%S')
                cv2.putText(m.array, ts, top_origin_2, font, scale, (0,0,0), thickness + 2)
                cv2.putText(m.array, ts, top_origin_2, font, scale, GREEN, thickness)
                message = f'{self.mse:.2f}/{self.MAX_MSE:.2f} ({self.average:.4f} -> {self.mse - self.average:.4f}/D{self.delta:.2f}) CF: ' \
                          f'{self.consecutive_frames} ISO: {gain:.02f} SS: {int(exp_time)} LUX: {lux:.05f}'
                text_color = GREEN if blue_motion else YELLOW
                cv2.putText(m.array, message, top_origin_1, font, scale, (0,0,0), thickness + 2)
                cv2.putText(m.array, message, top_origin_1, font, scale, text_color, thickness)
                if self.mse >= self.MAX_MSE:
                    cv2.circle(m.array, origin_red_dot, radius, RED, -1)
                if blue_motion:
                    cv2.circle(m.array, origin_blue_dot, radius, BLUE, -1)

        self.picam2.post_callback = add_mse
        self.picam2.start()
        self.picam2.start_encoder(self.encoder)
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

        buffer = RingBuffer(self.BUFFER_SIZE * 3)
        cframes = 0

        outfile = ''
        prev = None
        encoding = False
        end_time = None
        end_time_offset = timedelta(seconds=self.args.seconds)
        while True:
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
                if self.now.day != self.outdir_day:
                    self.set_outdir()

                if self.stop_at is not None and self.now >= self.stop_at:
                    print(f'Stop time {self.stop_at} reached...')
                    break
                # Measure pixels differences between current and
                # previous frame
                self.mse = np.square(np.subtract(cur, prev)).mean()
                self.average = buffer.append(self.mse)
                current_delta = self.mse - self.average
                # compare the average to the mse. If self.mse is N above average, motion detected
                if current_delta > self.delta:
                    if not encoding:
                        # if we start recording immediately we get a args.seconds second lead. consider waiting 2 seconds.
                        max_mse = self.mse
                        file_basename = f"{self.now.strftime('%Y%m%d-%H%M%S.%f')}_motion_{self.mse:.1f}"
                        outfile = os.path.join(self.tempdir, f"{file_basename}.h264")
                        self.encoder.output.fileoutput = outfile
                        self.encoder.output.start()
                        encoding = True
                        end_time = self.now + end_time_offset
                        print(f'Motion Detected: {outfile}, mse: {self.mse}')
                    else:
                        if self.mse > max_mse:
                            print(f' - MSE increased: {self.mse:.4f} delta: {current_delta:.4f}')
                            max_mse = self.mse
                    cframes += 1
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
                        discard = self.consecutive_frames < self.cf_threshold
                        if discard:
                            print(f'   - Less than {self.minmotion} seconds of motion. Discarding clip.')
                            discarding = 'discards'
                            if not self.debug_discard:
                                os.remove(outfile)
                        if not discard or self.debug_discard:
                            new_fname = os.path.join(self.outdir, discarding, f'{file_basename}_{max_mse:.1f}.h264')
                            os.rename(outfile, new_fname)
                        print(f'- Motion End : {new_fname} (CF: {self.consecutive_frames}/{self.cf_threshold})')
                        self.consecutive_frames = 0
                        # rename file to include max_mse
                        # TODO: delete file if max_mse below threshold?

            prev = cur
        self.picam2.stop_encoder()

    def set_outdir(self):
        now = datetime.now()
        self.outdir = now.strftime('/home/pi/exposures/%Y%m%d-motion2')
        os.makedirs(self.outdir, exist_ok=True)
        if self.debug_discard:
            os.makedirs(os.path.join(self.outdir, 'discards'))
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
