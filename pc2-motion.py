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

from pprint import *

class RingBuffer(object):
    def __init__(self, size_max):
        self.max = size_max
        self.data = []
        self.cur = 0
        self._is_full = False

    def append_full(self, x):
        self.data[self.cur] = x
        self.cur = (self.cur+1) % self.max

    def append(self,x):
        """append an element at the end of the buffer"""
        if self._is_full:
            self.append_full(x)
        else:
            self.data.append(x)
            if len(self.data) >= self.max:
                self._is_full = True

class FrameDataBuffer(RingBuffer):
    def __init__(self, size_max, clip_data:str):
        super().__init__(size_max)
        self.file = None
        self.filename = None
        self.clip_data = clip_data

    def is_writing(self):
        return self.file is not None

    def append(self, x):
        if self.file is None:
            self.data.append(x)
            if len(self.data) > self.max:
                self.data.pop(0)
        else:
            self.file.write(x + '\n')

    def start_clip(self, filename):
        self.filename = filename
        self.file = open(filename, 'w')
        self.file.write(f'CLIP: {self.clip_data}' + '\n')
        for frame in self.data:
            self.file.write(frame + '\n')
        # self.data = []

    def stop_clip(self):
        if self.file is not None:
            file = self.file
            self.file = None
            file.flush()
            file.close()
        self.data = []
        self.cur = 0
        self._is_full = False

class MotionAveragingBuffer(RingBuffer):
    """ class that implements a not-yet-full buffer """
    N = 1.5

    def __init__(self, size_max):
        super().__init__(size_max)
        self._total = 0
        self.average = None
        self._motion_detected = False

    @property
    def motion_detected(self):
        return self._motion_detected

    def append_full(self, x):
        """ Append an element overwriting the oldest one. """
        # If the new value is significantly bigger than the average, feed the average into the ring buffer so
        # that the average is not affected by the spikes.
        self._motion_detected = (x >= self.average * self.N)
        if self._motion_detected:
            # if motion is detected, don't increase the average by the full difference.
            x = self.average + (x - self.average) / 3

        old_x = self.data[self.cur]
        self._total += x - old_x
        super().append_full(x)

    def append(self,x):
        """append an element at the end of the buffer"""
        if not self._is_full:
            self._total += x
        super().append(x)
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

parser.add_argument('--exposure', type=int,
                    help='force the exposure speed (Microseconds). If fps frequent, it will be reduced')
parser.add_argument('--fps', type=int, default=30,
                    help='output video frames per second. If this is too high for the requested exposure time, '
                         'fps will be reduced. Default: 30. Faster values impact the motion detection algorithm')
parser.add_argument('--night-fps', type=int, default=15,
                    help='When the LUX drops below a certain level, force the camera FrameDurationLimits, ExposureTime, '
                         'FrameRate based on this value')
parser.add_argument("--lux-hi", type=float, default=3.0,
                    help="Highwater for night mode. (switch to day mode above this lux)")
parser.add_argument("--lux-lo", type=float, default=2.5,
                    help="Lowwater for night mode. (switch to night mode below this lux)")
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
    RAW_DIR_NAME = 'raw'

    def __init__(self, args):
        if self.CURRENT_CAMERA is not None:
            raise Exception('You can only have one camera at a time')
        self.CURRENT_CAMERA = self
        self.args = args
        self.lsize = (320,240)
        self._size = (width, height) # sizes are constrained. See variable definitions
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
        self.average_buffer = MotionAveragingBuffer(self.BUFFER_SIZE * 9)

        self.picam2 = Picamera2()
        # pprint(self.picam2.sensor_modes)

        # Track the "fps" of the loop and the callback (add_mse) so we know when we have overburdoned the callback
        self.loop_previous_time = None
        self.loop_fps = 0
        self.callback_previous_time = None
        self.callback_fps = 0

        # Use the latest LUX from the camera to check if we should be in daytime or nightime mode.
        self.lux = None
        self.nightmode = False
        self.night_exposure = int((1.0 / args.night_fps) * 1000000)
        print(f'NIGHT EXPOSURE: {self.night_exposure}')
        self.night_iso = 8.0
        self.scalar_crop = None

    def setup_night_mode(self):
        if self.nightmode:
            print(f'WARNING: setup_night_mode called in night mode')
            return
        print(f'### Start Night Mode: ISO: {self.night_iso:.2f}, EXP: {self.night_exposure}')
        self.nightmode = True
        self.picam2.stop()
        self.cf_threshold = args.night_fps * args.minmotion
        with self.picam2.controls as controls:
            controls.AeEnable = False
            controls.AwbEnable = False
            controls.FrameRate = args.night_fps
            controls.FrameDurationLimits = (self.night_exposure, self.night_exposure)
            controls.ExposureTime = self.night_exposure
            controls.AnalogueGain = self.night_iso
            # controls.AeExposureMode = libcamera.controls.AeExposureModeEnum.Long
            if self.scalar_crop is not None:
                controls.ScalerCrop = self.scalar_crop
        self.picam2.start()
        metadata = self.picam2.capture_metadata()
        print(f'NIGHT META: {metadata}')

    def setup_day_mode(self):
        if not self.nightmode:
            print(f'WARNING: setup_day_mode called in day mode')
            return
        print(f'### Start Day Mode')
        self.nightmode = False
        # exposure_time = int((1.0 / args.fps) * 1000000)
        self.cf_threshold = args.fps * args.minmotion
        with self.picam2.controls as controls:
            controls.AeEnable = True
            controls.AwbEnable = True
            controls.FrameRate = args.fps
            if args.custom:
                controls.AeExposureMode = libcamera.controls.AeExposureModeEnum.Custom
            else:
                controls.AeExposureMode = libcamera.controls.AeExposureModeEnum.Normal

            # controls.ExposureTime = exposure_time
            # controls.FrameDurationLimits = (exposure_time, exposure_time)
            if self.scalar_crop is not None:
                controls.ScalerCrop = self.scalar_crop
        metadata = self.picam2.capture_metadata()
        print(f'DAY METADATA: {metadata}')

    def setup(self):
        self.nightmode = False
        controls={
            'AeEnable': True,
            'AwbEnable': True,
            'NoiseReductionMode': libcamera.controls.draft.NoiseReductionModeEnum.HighQuality,
        }
        if args.custom:
            controls['AeExposureMode'] = libcamera.controls.AeExposureModeEnum.Custom

        controls["FrameRate"] = self.fps

        video_config = self.picam2.create_video_configuration(
            main={"size": self._size, "format": "RGB888"},
            lores={"size": self.lsize, "format": "YUV420"},
            controls=controls,


        )
        video_config['transform'] = libcamera.Transform(hflip=args.flip, vflip=args.flip)
        self.picam2.configure(video_config)

        # print(f'CONFIG: {self.picam2.camera_configuration()}')

        self.set_outdir()

    def start(self):
        self.picam2.start_preview()
        self.encoder = H264Encoder(10000000, repeat=True)
        # 5 seconds X FramesPerSecond
        print(f'BUFFER_SIZE = {self.BUFFER_SIZE} (fps: {self.fps}, seconds: {args.seconds}) MSE Threshold: {self.MAX_MSE}')
        self.encoder.output = CircularOutput(buffersize=self.BUFFER_SIZE)
        # fps here is just the fps for daytime, not the actual fps of an individule clip
        clip_data = f'version: 1, mse: {args.mse}, delta: {args.delta}, minmotion: {args.minmotion}, seconds: {args.seconds}, lux_lo: {args.lux_lo}, lux_hi: {args.lux_hi}, zoom: {args.zoom}, fps: {self.fps}'
        self.frame_data_buffer = FrameDataBuffer(self.BUFFER_SIZE, clip_data)
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
                self.lux = metadata['Lux'] if 'Lux' in metadata else 'NOLUX'
                exp_time = metadata['ExposureTime'] if 'ExposureTime' in metadata else 'NOEXP'
                fduration = metadata['FrameDuration'] if 'FrameDuration' in metadata else 'NODUR'
                gain = metadata['AnalogueGain']
                ts = datetime.strftime(now, '%Y/%m/%d %H:%M:%S.%f')

                motion = (self.mse - self.average > self.delta) or self.average_buffer.motion_detected
                if motion and not self.frame_data_buffer.is_writing():
                    self.frame_data_buffer.start_clip(self.file_basename + '_data.txt')

                # cv2.putText(m.array, ts, (left, y), font, scale, (0,0,0), thickness + 2)
                cv2.putText(m.array, ts, (left, y), font, scale, GREEN, thickness)
                nightmode = "night" if self.nightmode else "day"
                fps = args.night_fps if self.nightmode else self.fps
                message = (f'ISO: {gain * 100:.0f} SS: {int(exp_time)} FD: {int(fduration)} LUX: {self.lux:.02f} FPS: {fps:.1f} '
                           f'(loop: {int(self.loop_fps)} cb: {int(self.callback_fps)}) {nightmode}')
                text_color = GREEN
                y += ystep
                #cv2.putText(m.array, message, (left, y), font, scale, (0,0,0), thickness + 2)
                cv2.putText(m.array, message, (left, y), font, scale, text_color, thickness)

                motion_str = 'M' if motion else '_'
                frame_data = f'{ts},{fps},{self.lux:.2f},{self.mse:.4f},{self.average:.4f},{motion_str}'
                self.frame_data_buffer.append(frame_data)

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
                    if self.average_buffer is not None and self.average_buffer.motion_detected:
                        cv2.circle(m.array, origin_green_dot, radius, GREEN, -1)

        self.picam2.post_callback = add_mse
        self.picam2.start()
        # once the camera is started, we can read get it's max ISO (analogue gain) to set up for nightmode
        self.night_iso = self.picam2.camera_controls['AnalogueGain'][1]
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
            self.scalar_crop = (int(new_x), int(new_y), int(new_w), int(new_h))
            self.picam2.set_controls({
                'ScalerCrop': self.scalar_crop
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
        self.encoding = False
        end_time = None
        end_time_offset = timedelta(seconds=self.args.seconds)
        previous_minute = None
        TEST_NIGHT_MODE = False
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
                # "average" is the baseline level of motion (caused by wind, cloud shadows, etc)
                self.average = self.average_buffer.append(self.mse)
                date_time_string = self.now.strftime('%Y%m%d-%H%M%S.%f')
                current_delta = self.mse - self.average
                self.total_frames += 1
                # compare the average to the mse. If self.mse is N above average, motion detected
                # blue_motion = self.mse - self.average > self.delta
                if (current_delta > self.delta) or self.average_buffer.motion_detected:
                    if not self.encoding:
                        self.max_mse = self.mse
                        self.total_frames = 0
                        self.total_mse += self.mse
                        self.file_basename = f"{date_time_string}_motion_{self.mse:.1f}"
                        fps = args.night_fps if self.nightmode else self.fps
                        outfile = os.path.join(self.tempdir, f"{self.file_basename}_{fps}fps.h264")
                        self.encoder.output.fileoutput = outfile
                        # Start saving video buffer to file
                        self.encoder.output.start()
                        self.encoding = True
                        end_time = self.now + end_time_offset
                        print(f'Motion Detected: {outfile}, mse: {self.mse:.4f}')
                    else:
                        self.total_mse += self.mse
                        if self.mse > self.max_mse:
                            print(f' - MSE increased: {self.mse:.4f} delta: {current_delta:.4f} m: {(cframes + 1)/args.fps:.4f}')
                            self.max_mse = self.mse
                    cframes += 1
                    self.motion_frames += 1
                    if cframes > self.consecutive_frames:
                        self.consecutive_frames = cframes
                    if self.consecutive_frames >= self.cf_threshold:
                        end_time = self.now + end_time_offset

                else:
                    cframes = 0
                    if self.encoding and self.now > end_time:
                        # STOP saving video clip to file
                        self.encoder.output.stop()
                        self.encoding = False
                        self.frame_data_buffer.stop_clip()
                        new_file_name = ''
                        discarding = ''
                        am = self.total_mse / self.motion_frames if self.motion_frames > 0 else 100
                        # self.average_buffer.motion_detected is per frame, not per clip. Can we use it?
                        discard = ((self.consecutive_frames < self.cf_threshold) or (am < 0.9))
                        self.motion_frames = 0
                        if discard:
                            seconds = (1.0/args.fps) * self.consecutive_frames
                            print(f'   - Less than {self.minmotion} seconds of motion ({seconds:.2f}). Discarding clip. CF: {self.consecutive_frames} (T: {self.cf_threshold} AM: {am:.4f}')
                            discarding = 'discards'
                            if not self.debug_discard:
                                os.remove(outfile)
                                if self.frame_data_buffer.filename is not None and os.path.exists(self.frame_data_buffer.filename):
                                    os.remove(self.frame_data_buffer.filename)
                        if not discard or self.debug_discard:
                            d = f''
                            if discard:
                                d = f'-{self.consecutive_frames}-{am:.2f}'
                            fps = args.night_fps if self.nightmode else self.fps
                            new_file_name = os.path.join(self.outdir, discarding, f'{self.file_basename}_{self.max_mse:.1f}{d}_{fps}fps.h264')
                            os.rename(outfile, new_file_name)
                            if self.frame_data_buffer.filename is not None:
                                new_data_filename = os.path.join(self.outdir, discarding, self.frame_data_buffer.filename)
                                ### Move file rename to separate thread
                                os.rename(self.frame_data_buffer.filename, new_data_filename)
                        print(f'- Motion End : {new_file_name} (CF: {self.consecutive_frames}/{self.cf_threshold:.2f})')
                        self.consecutive_frames = 0
                        self.total_mse = 0
                        self.total_frames = 0
                        # rename file to include max_mse
                        # TODO: delete file if max_mse below threshold?

            prev = cur
            if not self.encoding:
                # only check for change in night mode when not encoding so that we do not change the frame rate in the
                # middle of a video clip
                # TODO : This isn't working. I still get clips where I see the camera go from night to day. I suspect
                #        it is because the circular buffer has extra frames when we end the clip or something similar
                # print(f'nm: {self.nightmode} lux: {self.lux} hi: {args.lux_hi} lo: {args.lux_lo}')
                if self.nightmode:
                    if self.lux >= args.lux_hi:
                        self.setup_day_mode()
                else:
                    if self.lux <= args.lux_lo:
                        self.setup_night_mode()

        self.picam2.stop_encoder()
        self.frame_data_buffer.stop_clip()

    def set_outdir(self):
        now = datetime.now()
        self.outdir = now.strftime(f'/home/pi/exposures/%Y%m%d-motion2/{self.RAW_DIR_NAME}')
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
