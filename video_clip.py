import logging
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

    def merge(self, other_clip):
        me_first = self.start_time < other_clip.start_time

        self.start_time = min(other_clip.start_time, self.start_time)
        if self.finished and other_clip.finished:
            self._end_time = min(self.end_time, other_clip.end_time)
        if self.has_motion:
            if other_clip.has_motion:
                self.first_motion = min(self.first_motion, other_clip.first_motion)
                self.last_motion = max(self.last_motion, other_clip.last_motion)
            else:
                self.first_motion = other_clip.first_motion
                self.last_motion = other_clip.last_motion
        self.finished = self.finished and other_clip.finished
        if me_first:
            self._filelist.append(other_clip.filename)
        else:
            self._filelist.insert(other_clip.filename, 0)


    @property
    def filename(self):
        return self._filename

    @property
    def end_time(self):
        return self._end_time

    @property
    def has_motion(self):
        return self.first_motion is not None

    @property
    def has_early_motion(self):
        if self.has_motion:
            return (self.first_motion - self.start_time) <= self.EARLY_DURATION
        return False

    @property
    def has_late_motion(self):
        if self.has_motion and self.finished:
            return (self._end_time - self.last_motion) <= self.EARLY_DURATION
        return False

    def finish(self):
        self._end_time = datetime.now()
        self.finished = True

    def add_motion_detection(self, motion_time):
        if motion_time < self.start_time:
            return False
        if self.finished and (motion_time > self._end_time):
            return False
        if self.first_motion is None:
            self.first_motion = motion_time
        self.last_motion = motion_time
        self._end_time = max(motion_time + self.motion_duration, self._end_time)
        return True