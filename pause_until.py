import threading
from datetime import datetime
import sys
import time as pytime

def pause_until(time, event:threading.Event):
    """
    Pause your program until a specific end time.
    'time' is either a valid datetime object or unix timestamp in seconds (i.e. seconds since Unix epoch)
    """
    end = time

    # Convert datetime to unix timestamp and adjust for locality
    if isinstance(time, datetime):
        # If we're on Python 3 and the user specified a timezone, convert to UTC and get tje timestamp.
        if sys.version_info[0] >= 3 and time.tzinfo:
            end = time.astimezone(time.timezone.utc).timestamp()
        else:
            zoneDiff = pytime.time() - (datetime.now()- datetime(1970, 1, 1)).total_seconds()
            end = (time - datetime(1970, 1, 1)).total_seconds() + zoneDiff

    # Type check
    if not isinstance(end, (int, float)):
        raise Exception('The time parameter is not a number or datetime object')

    # Now we wait
    while True:
        now = pytime.time()
        diff = end - now

        #
        # Time is up!
        #
        if event.is_set() or diff <= 0:
            break
        else:
            # 'logarithmic' sleeping to minimize loop iterations
            event.wait(diff / 2)
