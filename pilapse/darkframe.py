import cv2
import imutils
import numpy
import logging

from pilapse import colors

def get_contours(darkimage, threshold=6):
    # get locations of bad pixels
    darkgray = cv2.cvtColor(darkimage, cv2.COLOR_BGR2GRAY)
    (T, thresh) = cv2.threshold(darkgray, threshold, 255, cv2.THRESH_BINARY)
    contours = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_TC89_L1)
    contours = imutils.grab_contours(contours)

    return contours, darkgray

def apply_darkframe(image, contours, highlight=False):
    outimage = image.copy()
    # find the 'average' color of the input image
    avg_color_per_row = numpy.average(image, axis=0)
    avg_color = numpy.average(avg_color_per_row, axis=0)

    for c in contours:
        (x, y, w, h) = cv2.boundingRect(c)
        if False:
            x -= 1
            y -= 1
            w += 2
            h += 2
        logging.debug(f'Contour: {(x, y)}, {(x + w, y + h)}')
        cv2.rectangle(outimage, (x, y), (x + w, y + h), avg_color, cv2.FILLED)
        if highlight:
            cv2.rectangle(outimage, (x, y), (x + w, y + h), colors.GREEN)

    return outimage
