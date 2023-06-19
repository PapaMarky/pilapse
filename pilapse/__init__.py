import logging
import os
import signal
import sys
import time

import cv2

import pilapse.motion
import pilapse.colors

# TODO Incorporate all of this "time to die" stuff into App class so it can have access to the shutdown event
time_to_die = False
def it_is_time_to_die():
    logging.debug(f'Is it time_to_die?: {time_to_die}')
    return time_to_die

def set_time_to_die():
    global time_to_die
    logging.debug('Setting "time_to_die"')
    time_to_die = True

def exit_gracefully(signum, frame):
    logging.info(f'SHUTTING {get_program_name()} DOWN due to {signal.Signals(signum).name}')
    set_time_to_die()

signal.signal(signal.SIGINT, exit_gracefully)
signal.signal(signal.SIGTERM, exit_gracefully)

def get_program_name():
    name = os.path.basename(sys.argv[0])
    s = name.split('.')
    if s[-1] == 'py':
        name = '.'.join(s[:-1])
    return name

def get_pid_file():
    return f'{get_program_name()}.pid'

def create_pid_file():
    pidfile = get_pid_file()
    if os.path.exists(pidfile):
        logging.error('PID file exists. Already running?')
        pid_in_use = True
        with open(pidfile) as f:
            pid = f.read().strip()
            try:
                pid = int(pid)
                if not psutil.pid_exists(pid):
                    logging.info(f'No process is using that PID ({pid}). Taking over the file')
                    pid_in_use = False
            except:
                logging.warning(f'PID in file is bad. Taking over the file.')
                pid_in_use = False
        if pid_in_use:
            return False
    with open(get_pid_file(), 'w') as pidout:
        pid = os.getpid()
        logging.info(f'saving PID ({pid}) in {pidfile}')
        pidout.write(f'{pid}')
    return True

def delete_pid_file():
    pidfile = get_pid_file()
    logging.info(f'Deleting PID file: {pidfile}')
    if os.path.exists(pidfile):
        logging.debug(f' - found {pidfile}')
        with open(pidfile) as f:
            pid = int(f.read())
            if os.getpid() != pid:
                logging.warning(f'PID file exists but contains "{pid}" (my pid is {os.getpid()})')
                return
        logging.debug(f' - deleting {pidfile}')
        os.remove(pidfile)

def die(status=0):
    logging.info(f'Time to die')
    delete_pid_file()
    time.sleep(0.1) # do not want this sleep to be interruptible
    sys.exit(status)

logfile = os.environ.get('LOGFILE')
if not logfile:
    logfile = f'{get_program_name()}.log'
if logfile == 'stdout':
    logfile = None

print(f'Logging to {logfile}')

def annotate_frame(image, annotation, config, position='ul', text_size:float = 1.0):
    if annotation:
        text_height = int(config.height / 25 * text_size)
        space = text_height * 0.5
        thickness = int(config.height * 1/480 * text_size)
        if thickness < 1:
            thickness = 1

        font = cv2.FONT_HERSHEY_SIMPLEX
        text_size, baseline = cv2.getTextSize(annotation, font, 1, 3)

        image_h, image_w, _ = image.shape
        x = text_height
        y = 2 * text_height

        scale = text_height / text_size[1]
        color = config.label_rgb if config.label_rgb is not None else colors.ORANGE

        logging.debug(f'pos: {position}, str: "{annotation}"')
        lines = annotation.splitlines()
        nlines = len(lines)

        if position[1] in 'lL':
            x = text_height
        elif position[1] in 'rR':
            x = image_w - ((text_height + text_size[0]) * scale)

        if position[0] in 'uUtT':
            y = 2 * text_height
        elif position[0] in 'lLbB':
            y = image_h - nlines * (text_height + space) - text_height

        logging.debug(f'annotation origin for {position}')
        for line in lines:
            origin = (int(x), int(y))
            # first write with greater thickness to create constrasting outline
            cv2.putText(image, line, origin, font, scale, colors.WHITE, thickness=thickness + 2)
            cv2.putText(image, line, origin, font, scale, color, thickness=thickness)
            y += text_height + space
        return text_height
