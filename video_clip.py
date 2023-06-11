import logging
from datetime import datetime, timedelta


class VideoClip:
    def __init__(self, filename, duration=timedelta(seconds=3)):
        self.start_time:datetime = datetime.now()
        self._filename = filename
        self._end_time:datetime = self.start_time + duration
        self.first_motion:datetime = None
        self.last_motion:datetime = None
        self.motion_duration:timedelta = timedelta(seconds=3)
        self.finished = False

    @property
    def filename(self):
        return self._filename

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
        if self.finished:
            logging.error(f'Adding motion to finished video clip')
            return

        if self.first_motion is None:
            self.first_motion = motion_time
        self.last_motion = motion_time
        self._end_time = max(motion_time + self.motion_duration, self._end_time)
