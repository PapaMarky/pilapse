import argparse
import glob
import os
import subprocess

import cv2

from pilapse import colors
from pilapse.darkframe import get_contours
from pilapse.motion import MotionDetector
from pilapse.threads import FileImage

def get_value(name, value):
    print(f'{name} is currently set to {value}')
    new_value = input(f'Enter new value for {name}: ')
    if new_value == '.':
        print(f'{name} not changed.')
        return value
    print(f'{name} is now set to {new_value}')
    return new_value
def key_help():
    print('SPACE: toggle pause')
    print('    b: back one frame (sets "paused")')

commands = {
    '?': 'Help: show this message',
    ' ': 'Toggle Pause',
    'q': 'Quit',
    '-': 'Show Difference between images',
    'B': 'Run Backwards',
    'F': 'Run Forewards',
    'R': 'Reverse direction and run in the the other direction',
    'f': 'Go foreward one frame. Right-Arrow works too (Pauses)',
    'b': 'Go back one frame. Left-Arrow works too (Pauses)',
    'BACK_ARROW': 'Go back one frame. (Pauses)',
    'o': 'Open the image in preview',
    'd': 'Toggle debug mode (show rects of all "movement")',
    'm': 'Toggle show motion (show rects of "movement" that match criteria'
}

def show_help():
    print('--- COMMANDS ---')
    for cmd in commands:
        print(f"'{cmd}' : {commands[cmd]}")

def detect_stuff(filelist, window_name):
    MINDIFF = int(os.environ.get('MINDIFF', 500))
    THRESHOLD = int(os.environ.get('THRESHOLD', 5))
    DILATION = int(os.environ.get('DILATION', 3))
    TOP = float(os.environ.get('TOP', 0.0))
    BOTTOM = float(os.environ.get('BOTTOM', 1.0))
    LEFT = float(os.environ.get('LEFT', 0.0))
    RIGHT = float(os.environ.get('RIGHT', 1.0))

    md = MotionDetector(
        'night-motion',
        MINDIFF,
        TOP, LEFT, BOTTOM, RIGHT,
        DILATION,
        THRESHOLD,
        show_motion=True,
        blur_size=None,
        save_diffs=True,
        debug=True
    )
    previous_image = None
    paused = False
    direction = 1 # set to -1 to play frames backwards
    cv2.imshow(window_name, cv2.imread(filelist[0]))
    def handle_mindiff_slider(new_mindiff):
        print(f'new mindiff: {new_mindiff}')
        md.mindiff = new_mindiff
    def handle_threshold_slider(new_threshold):
        md.threshold = new_threshold
    def handle_dilation_slider(new_dilation):
        md.threshold = new_dilation

    print('Create Slider')
    cv2.createTrackbar('MINDIFF', window_name, MINDIFF, 500, handle_mindiff_slider)
    cv2.createTrackbar('THRESHOLD', window_name, THRESHOLD, 100, handle_threshold_slider)
    cv2.createTrackbar('DILATION', window_name, DILATION, 15, handle_dilation_slider)

    paused = True
    show_diff = False
    file_count = len(filelist)
    i = 0
    while i < file_count:
        file = filelist[i]
        dir = '<--' if direction < 0 else '-->'
        cv2.setWindowTitle(window_name, f'{i} / {file_count} : {dir} : {file}')
        img = cv2.imread(file)
        # print(f'{i} : {file}')
        current_image = FileImage(file, image=img)
        if previous_image is not None:
            try:
                motion_data = md.compare_images(previous_image, current_image)
            except Exception as e:
                print(f'EXCEPETION: {e}')
                print(f'{i} : {dir} : {file}')
                i += direction
                break
            if motion_data.motion_detected:
                #print(f'Motion detected, Pausing...')
                paused = True
            if paused:
                wait = 0
            else:
                wait = 200
            if show_diff:
                shown_image = motion_data.diff2_image.image
            else:
                shown_image = motion_data.motion_image
            cv2.imshow(window_name, shown_image)
            raw_key = cv2.waitKey(wait)
            key = chr(raw_key & 0xFF)
            if key == 'q':
                break
            if key == '?':
                show_help()
                continue
            elif key == '-': # show diffs
                show_diff = not show_diff
                continue
            elif key == ' ': # toggle pause
                paused = not paused
                print(f'Paused: {paused}')
                i += direction
                continue
            elif raw_key == 66: # 'B' go backwards
                direction = -1
                continue
            elif raw_key == 70: # 'F' go forwards
                direction = 1
                continue
            elif raw_key == 82: # 'R' reverse direction
                direction = direction * -1
                continue
            elif raw_key == 98 or raw_key == 2: # 'b' or <-- (back)
                paused = True
                if i > 0:
                    i -= 1
                    if i > 0:
                        img = cv2.imread(filelist[i-1])
                        previous_image = FileImage(filelist[i-1], image=img)
                continue
            elif raw_key == 102 or raw_key == 3: # 'f' or --> (forward)
                paused = True
                if i < file_count - 1:
                    i += 1
                    previous_image = current_image
                continue
            elif raw_key == 111: # 'o' (open)
                p = subprocess.run(['open', current_image.filepath])
                paused = True
                continue
            elif raw_key == 100: # 'd' toggle debug
                md.debug = not md.debug
                print(f'Toggle Debug to {md.debug}')
                continue
            elif raw_key == 109: # 'm' toggle debug
                md.show_motion = not md.show_motion
                print(f'Toggle Show Motion to {md.show_motion}')
                continue
            elif raw_key != -1:
                print('-----------')
                print(f'UNKNOWN KEY COMMAND: {raw_key} "{chr(raw_key)}"')
                show_help()

            if not paused:
                i += direction
                if i < 0:
                    i = 0
                    paused = True
                if i >= file_count:
                    i = file_count - 1
                    paused = True

        previous_image = current_image

def detect_stuff2(filelist, window_name):
    for file in filelist:
        image1 = cv2.imread(file)
        H, W, _ = image1.shape
        image = image1.copy()
        contours, grayimage = get_contours(image, threshold=args.threshold)
        # print(f'len contours: {len(contours)}')

        max_size = 0
        for c in contours:
            (x, y, w, h) = cv2.boundingRect(c)
            if abs(W - w) > 10 and w > max_size:
                max_size = w
            if abs(H - h) > 10 and h > max_size:
                max_size = h
            cv2.rectangle(image, (x, y), (x + w, y + h), colors.GREEN)
        cv2.imshow(window_name, image)
        wait = 200
        if max_size > 100:
            print(f'MAX C: {max_size} ({W} x {H})')
            wait = 0
        key = cv2.waitKey(wait)

        if key != -1:
            print(f'KEY: {key}')
            break

if __name__ == '__main__':
    parser = argparse.ArgumentParser('Find interesting things in nightsky timelapse')
    parser.add_argument('--type', type=str, help='type of image files (default: "jpg")', default='jpg')
    parser.add_argument('imgdir', type=str, help='Directory containing images')
    args = parser.parse_args()
    IMAGE_DIR = args.imgdir

    filelist = glob.glob(os.path.join(IMAGE_DIR, f'*.{args.type}') )
    filelist.sort()
    window_name = f'Press Any Key to Close ("?" for help)'
    detect_stuff(filelist, window_name)
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL | cv2.WINDOW_KEEPRATIO | cv2.WINDOW_GUI_EXPANDED)
    cv2.destroyAllWindows()

