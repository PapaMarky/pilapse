import argparse
import logging
import subprocess
import sys

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
import pathlib
import sys

import cv2
from pilapse.darkframe import apply_darkframe

if __name__ == '__main__':
    parser = argparse.ArgumentParser('Test the "apply_darkframe" function')
    parser.add_argument('--image', '-i', type=pathlib.Path, required=type,
                        help='Path to an image with the hot pixel issue')
    parser.add_argument('--darkimage', '-d', type=pathlib.Path, required=True,
                        help='Path to the dark frame to use for cleaning up the image')
    parser.add_argument('--output', '-o', type=pathlib.Path, default='output.jpg',
                        help='Path to write the cleaned up image to. Default: "output.jpg')
    parser.add_argument('--threshold', '-t', type=int, default=7,
                        help='Threshold determines how large of a defect to try to fix')
    parser.add_argument('--highlight', '-H', action='store_true',
                        help='Draw rectangles around the bad pixels in the output. '
                             'Use this to help choose other values')
    parser.add_argument('--show', '-s', action='store_true',
                        help='Open the output image when done.')
    parser.add_argument('--open', action='store_true',
                        help='MAC ONLY: call "open" on the image')
    config = parser.parse_args()

    print(config)

    image_in:pathlib.Path = config.image
    if not image_in.exists():
        parser.print_help()
        logging.error('IMAGE must be a path to a file that exists.')
        sys.exit(1)
    dark_img:pathlib.Path = config.darkimage
    if not dark_img.exists():
        parser.print_help()
        logging.error('IMAGE must be a path to a file that exists.')
        sys.exit(1)
    logging.info(f'IMAGE: {image_in}')
    logging.info(f'DARKIMAGE: {image_in}')
    img = cv2.imread(f'{image_in}')
    dark_img = cv2.imread(f'{dark_img}')

    outimage = apply_darkframe(img, dark_img, highlight=config.highlight, threshold=config.threshold)
    logging.info(f'Writing cleaned up image to {config.output}')
    cv2.imwrite(f'{config.output}', outimage)
    if config.show:
        window_name = f'Press Any Key to Close'
        cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
        cv2.imshow(window_name, outimage)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    if config.open:
        subprocess.Popen(f'open {config.output}'.split(' '))