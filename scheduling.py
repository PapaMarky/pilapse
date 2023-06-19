import argparse
import logging
from datetime import datetime, timedelta
from datetime import time

from config import Configurable
from suntime import Suntime, BadTimeString


class Schedule(Configurable):
    """
    Class for scheduling when the program should run.

    Client must use argparse to set up command line
    """
    ARGS_ADDED = False
    @classmethod
    def add_arguments_to_parser(cls, parser:argparse.ArgumentParser, argument_group_name:str='Scheduling')->argparse.ArgumentParser:
        if Schedule.ARGS_ADDED:
            return parser

        scheduling = parser.add_argument_group(argument_group_name, 'Control when to run and when to stop')
        scheduling.add_argument('--stop-at', type=str, default=None,
                            help='Stop running (exit) the next time the time reaches "stop-at". '
                                 'Format: HH:MM:SS with HH in 24 hour format or a suntime. (see Suntime.valid_times()')
        scheduling.add_argument('--run-from', type=str, default=None,
                            help='Only run after this time of day. (Format: HH:MM:SS with HH in 24 hour format) '
                                 'Pause (don not exit) if before this time')
        scheduling.add_argument('--run-until', type=str, default=None,
                            help='Only run until this time of day. (Format: HH:MM:SS with HH in 24 hour format)'
                                 'Pause (don not exit) if after this time')
        scheduling.add_argument('--location', type=str, default=None,
                                help='Location to use for looking up values like "sunrise"')
        Schedule.ARGS_ADDED = True
        return parser

    def __init__(self, config:argparse.Namespace):
        self._stopped:bool = False
        self._paused:bool = False if config.run_from is None else True

        self._suntimes = None
        logging.info(f'location: {config.location}')
        self._location = config.location

        def value_to_time(value):
            if not ':' in value:
                value = self.suntimes.value_from_name(value)
                if value is None:
                    raise BadTimeString(value)
                return value
            (hour, minute, second) = config.stop_at.split(':')
            return datetime.now().replace(hour=int(hour), minute=int(minute), second=int(second), microsecond=0)

        # validate config
        if config.stop_at is not None and (config.run_from is not None or config.run_until is not None):
            error_message = 'If stop-at is set, run-until and run-from cannot be set'
            raise Exception(error_message)

        if config.run_from is not None or config.run_until is not None:
            # if either are set, both must be set.
            if config.run_from is None or config.run_until is None:
                error_message = 'if either run-from or run-until are set, both must be set'
                raise Exception(error_message)

        self.stop_at:datetime = None
        if config.stop_at is not None:
            logging.debug(f'Setting stop-at: {config.stop_at}')
            self.stop_at = value_to_time(config.stop_at)
            if datetime.now() > self.stop_at:
                self.stop_at += timedelta(days=1)
            logging.debug(f'stop at : {self.stop_at}')

        self.run_from:time = None
        if config.run_from is not None:
            logging.info(f'Setting run-from: {config.run_from}')
            try:
                self.run_from = datetime.strptime(config.run_from, '%H:%M:%S').time()
            except Exception as e:
                logging.exception('Exception while parsing "run_from" ({config.run_from})')
                raise e
            logging.info(f' - run-from is {self.run_from}')

        self.run_until:time = None
        if config.run_until is not None:
            logging.debug(f'Setting run-until: {config.run_until}')
            try:
                self.run_until = datetime.strptime(config.run_until, '%H:%M:%S').time()
            except Exception as e:
                logging.exception(f'Exception while parsing "run_until" ({config.run_until})')
                raise e
            logging.info(f' - run-until is {self.run_until}')

    @property
    def location(self):
        return self._location

    @property
    def suntimes(self):
        if self._suntimes is None:
            self._suntimes = Suntime(self.location)
        return self._suntimes

    @property
    def paused(self):
        return self._paused

    @property
    def stopped(self):
        return self._stopped

    def get_suntime(self, suntime):
        if str not in self.suntimes.valid_times():
            logging.error(f'bad suntime value: {suntime}')
            return None
        return self.suntimes.value_from_name(suntime)

    def update(self):
        """
        Update state of "paused" and "stopped". Should be called at beginning of client's loop.
        :return:
        """
        now = datetime.now()
        self._check_paused(now)
        self._check_stop_at(now)

    def _check_stop_at(self, now:datetime):
        """
        Update "stopped" based on "stop_at"
        :param now: Current time (or time to check)
        :return:
        """
        if self.stop_at is not None and now > self.stop_at:
            self._stopped = True

    def _check_paused(self, now:datetime):
        """
        Update "paused" state based on "run_from" and "run_until"
        :param now: Current Time (or time to check)
        :return:
        """
        current_time = now.time()
        logging.debug(f'current time: {current_time}, from {self.run_from}, until {self.run_until}')
        if self.run_until is not None and not self.paused:
            if current_time >= self.run_until or current_time <= self.run_from:
                logging.info(f'Pausing because outside run time: from {self.run_from} until {self.run_until}')
                self._paused = True
        if self.paused:
            if current_time >= self.run_from and current_time <= self.run_until:
                logging.info(f'Ending pause because inside run time: from {self.run_from} until {self.run_until}')
                self._paused = False
