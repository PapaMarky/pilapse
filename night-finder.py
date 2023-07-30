import argparse
import glob
import os

import cv2

from pilapse import colors
from pilapse.darkframe import get_contours
from pilapse.motion import MotionDetector
from pilapse.threads import FileImage


def detect_stuff(filelist, window_name):
    MINDIFF = 500
    THRESHOLD=5
    DILATION=3
    TOP=0.0
    BOTTOM=1.0
    LEFT=0.0
    RIGHT=1.0
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
    for file in filelist:
        img = cv2.imread(file)
        # print(f'{file}')
        current_image = FileImage(file, image=img)
        if previous_image is not None:
            motion_data = md.compare_images(previous_image, current_image)
            if motion_data.motion_detected:
                cv2.imshow(window_name, motion_data.motion_image)
                wait = 0
            else:
                # cv2.imshow(window_name, current_image.image)
                cv2.imshow(window_name, motion_data.motion_image)
                wait = 100
            key = cv2.waitKey(wait)
            if key == 113: # 'q'
                break
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
    parser.add_argument('--threshold', type=int, help='shape detection threshold', default=6)
    parser.add_argument('--type', type=str, help='type of image files (default: "jpg")', default='jpg')
    parser.add_argument('imgdir', type=str, help='Directory containing images')
    args = parser.parse_args()
    IMAGE_DIR = args.imgdir

    filelist = glob.glob(os.path.join(IMAGE_DIR, f'*.{args.type}') )
    filelist.sort()
    window_name = f'Press Any Key to Close'
    detect_stuff(filelist, window_name)
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.destroyAllWindows()

