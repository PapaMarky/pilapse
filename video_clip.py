import logging
import os.path
from datetime import datetime, timedelta


class VideoClip:
    EARLY_DURATION = timedelta(seconds=1) # motion within EARLY_DURATION of start time is "early motion"

    def __init__(self, filename, duration=timedelta(seconds=5)):
        self.start_time:datetime = datetime.now()
        self._filelist = [filename]
        self._end_time:datetime = self.start_time + duration
        self.first_motion:datetime = None
        self.last_motion:datetime = None
        self.motion_duration:timedelta = duration
        self.finished = False
        self._framerate = None

    def to_string(self):
        return f'{os.path.basename(self.filename)} {len(self._filelist)} clips ' \
               f'{self.start_time.strftime("%Y%m%d_%H%M%S.%f")} to {self.end_time.strftime("%Y%m%d_%H%M%S.%f")} ' \
               f'motion: {self.has_motion}'

    def merge(self, other_clip):
        logging.info(f'Merging:')

        logging.info(f'{other_clip.to_string()} into ')
        logging.info(f'{self.to_string()}')
        me_first = self.start_time < other_clip.start_time

        self.start_time = min(other_clip.start_time, self.start_time)
        if self.finished and other_clip.finished:
            self._end_time = max(self.end_time, other_clip.end_time)
        if self.has_motion:
            if other_clip.has_motion:
                self.first_motion = min(self.first_motion, other_clip.first_motion)
                self.last_motion = max(self.last_motion, other_clip.last_motion)
        elif other_clip.has_motion:
            self.first_motion = other_clip.first_motion
            self.last_motion = other_clip.last_motion

        self.finished = self.finished and other_clip.finished

        self._filelist += other_clip._filelist
        self._filelist.sort()

        logging.info(f'post merge filelist: {self._filelist}')
        logging.info(f'start: {self.start_time.strftime("%Y%m%d_%H%M%S.%f")} end: {self.end_time.strftime("%Y%m%d_%H%M%S.%f")}')
        if self.has_motion:
            logging.info(f'motion: first {self.first_motion.strftime("%Y%m%d_%H%M%S.%f")} '
                         f'last {self.last_motion.strftime("%Y%m%d_%H%M%S.%f")}')
        else:
            logging.info(f'no motion {self.first_motion} {self.last_motion}')

    @property
    def framerate(self):
        return self._framerate

    @framerate.setter
    def framerate(self, rate):
        self._framerate = rate

    @property
    def filename(self):
        return self._filelist[0]

    @property
    def end_time(self):
        return self._end_time

    @property
    def has_motion(self):
        return self.first_motion is not None

    def finish(self):
        self._end_time = datetime.now()
        self.finished = True

    def add_motion_detection(self, motion_time):
        if motion_time < self.start_time:
            logging.info(f'Motion too early (motion: {motion_time} vs start {self.start_time})')
            return False
        if self.finished and (motion_time > self._end_time):
            logging.info(f'Motion too late (motion {motion_time} vs end {self.end_time})')
            return False
        logging.info(f'Updating motion time of {os.path.basename(self.filename)}')
        if self.first_motion is None:
            self.first_motion = motion_time
        self.last_motion = motion_time
        self._end_time = max(motion_time + self.motion_duration, self._end_time)
        return True