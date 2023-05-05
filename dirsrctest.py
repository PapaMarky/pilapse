import sys

import watchdog.events
import watchdog.observers
import time


class Handler(watchdog.events.PatternMatchingEventHandler):
    def __init__(self):
        # Set the patterns for PatternMatchingEventHandler
        watchdog.events.PatternMatchingEventHandler.__init__(self, patterns=['*.png'],
                                                             ignore_directories=True, case_sensitive=False)

    def on_created(self, event):
        print(f"Watchdog received created event - {event.src_path}")
    # Event is created, you can process it now


if __name__ == "__main__":
    src_path = sys.argv[1]
    event_handler = Handler()
    observer = watchdog.observers.Observer()
    observer.schedule(event_handler, path=src_path, recursive=True)
    observer.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
