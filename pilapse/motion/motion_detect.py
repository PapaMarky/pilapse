import logging
import os

import cv2
import imutils

from pilapse import colors
from threads import FileImage, Image


class MotionData:
    def __init__(self):
        self._motion_detected:bool = False
        self._motion_image:Image = None
        self._contours = None
        self._diff_image:FileImage = None
        self._diff2_image:FileImage = None
        self._gray_image:FileImage = None
        self._dilated_image:FileImage = None
        self._threshold_image:FileImage = None

    @property
    def motion_detected(self):
        return self._motion_detected
    @motion_detected.setter
    def motion_detected(self, value:bool):
        self._motion_detected = value

    @property
    def contours(self):
        return self._contours
    @contours.setter
    def contours(self, value):
        self._contours = value

    @property
    def diff_image(self):
        return self._diff_image
    @diff_image.setter
    def diff_image(self, new_diff:FileImage):
        self._diff_image = new_diff

    @property
    def diff2_image(self):
        return self._diff2_image
    @diff2_image.setter
    def diff2_image(self, new_diff2:FileImage):
        self._diff2_image = new_diff2

    @property
    def gray_image(self):
        return self._gray_image
    @gray_image.setter
    def gray_image(self, new_gray:FileImage):
        self._gray_image = new_gray

    @property
    def dilated_image(self):
        return self._dilated_image
    @dilated_image.setter
    def dilated_image(self, new_dilated:FileImage):
        self._dilated_image = new_dilated

    @property
    def threshold_image(self):
        return self._threshold_image
    @threshold_image.setter
    def threshold_image(self, new_threshold:FileImage):
        self._threshold_image = new_threshold

class MotionDetector:
    def __init__(self,
                 outdir:str,
                 mindiff:int,
                 top:float, left:float, bottom:float, right:float,
                 dilation:int,
                 threshold:int,
                 save_diffs:bool=False,
                 shrink_to:int=None,
                 blur_size:int=10,
                 debug:bool=False,
                 show_motion:bool=False):
        self.outdir = outdir
        self.mindiff = mindiff
        self.top = top
        self.left = left
        self.bottom = bottom
        self.right = right
        self.dilation = dilation
        self.threshold = threshold
        self.save_diffs = save_diffs
        self.shrink_to = shrink_to
        self.blur_size = blur_size
        self.debug = debug
        self.show_motion = show_motion

    def compare_images(self, previous_image:Image, current_image:Image):
        fname_base = current_image.base_filename
        height, width, _ = current_image.image.shape
        #resize the images to make them smaller. Bigger image may take a significantly
        #more computing power and time
        previous_image = previous_image.image
        image_in = current_image.image.copy()
        motion_data = MotionData()

        ### Try blurring the source images to reduce lots of small movement (wind) from registering
        # TODO: compare results with and without
        if self.blur_size is not None:
            previous_image = cv2.blur(previous_image, (self.blur_size, self.blur_size))
            new_image = cv2.blur(current_image, (self.blur_size, self.blur_size))
            if self.save_diffs:
                blur_name = f'{fname_base}_00B.jpg'
                path = os.path.join(self.outdir, blur_name)
                logging.info(f'Adding {path} to motion data')
                motion_data.diff_image = FileImage(path, image=new_image)

        scale = 1.0
        if self.shrinkto is not None:
            scale  = height / self.shrinkto
            previous_image = imutils.resize(previous_image.copy(), height = self.shrinkto)
            new_image = imutils.resize(new_image.copy(), height = self.shrinkto)

        sMindiff = int(self.mindiff / scale)
        sLeft = int(self.left / scale)
        sRight = int(self.right / scale)
        sTop = int(self.top / scale)
        sBottom = int(self.bottom / scale)

        diff = previous_image.copy()
        cv2.absdiff(previous_image, new_image, diff)
        # 01 - diff
        if self.save_diffs:
            diff2 = diff.copy()
            if self.shrink_to is not None:
                diff2 = imutils.resize(diff2, height)
            diff_name = f'{fname_base}_01D.jpg'
            path = os.path.join(self.outdir, diff_name)
            motion_data.diff2_image = FileImage(path, image=diff2)

        #converting the difference into grascale
        gray = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
        # 02 - gray
        if self.save_diffs:
            gray2 = gray.copy()
            if self.shrink_to is not None:
                gray2 = imutils.resize(gray2, height)
            gray_name = f'{fname_base}_02G.jpg'
            path = os.path.join(self.outdir, gray_name)
            motion_data.gray_image = FileImage(path, image=gray2)

        #increasing the size of differences so we can capture them all
        #for i in range(0, 3):
        dilated = gray.copy()
        #for i in range(0, 3):
        #    dilated = cv2.dilate(dilated, None, iterations= i+ 1)

        dilated = cv2.dilate(dilated, None, iterations= self.dilation)
        # 03 - dilated
        if self.save_diffs:
            dilated2 = dilated.copy()
            dilated2 = imutils.resize(dilated2, height)
            dilated_name = f'{fname_base}_03D.jpg'
            path = os.path.join(self.outdir, dilated_name)
            motion_data.dilated_image = FileImage(path, image=dilated2)

        #threshold the gray image to binarise it. Anything pixel that has
        #value more than 3 we are converting to white
        #(remember 0 is black and 255 is absolute white)
        #the image is called binarised as any value less than 3 will be 0 and
        # all values equal to and more than 3 will be 255
        # (T, thresh) = cv2.threshold(dilated, 3, 255, cv2.THRESH_BINARY)
        (T, thresh) = cv2.threshold(dilated, self.threshold, 255, cv2.THRESH_BINARY)

        # 04 - threshed
        if self.save_diffs:
            thresh2 = thresh.copy()
            thresh2 = imutils.resize(thresh2, height)
            thresh_name = f'{fname_base}_04T.jpg'
            path = os.path.join(self.outdir, thresh_name)
            motion_data.threshold_image = FileImage(path, image=thresh2)

        # thresh = cv2.bitwise_not(thresh)
        # now we need to find contours in the binarised image
        # cnts = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
        cnts = cv2.findContours(thresh, cv2.RETR_LIST, cv2.CHAIN_APPROX_TC89_L1)
        cnts = imutils.grab_contours(cnts)
        motion_data.contours = cnts

        copy = None
        def get_copy(copy):
            if copy is None:
                copy = image_in.copy()
            return copy

        height, width, _ = new_image.shape
        if self.debug:
            copy = get_copy(image_in)
            cv2.rectangle(image_in, (sLeft, sTop), (sRight, sBottom), colors.RED)
        for c in cnts:
            # fit a bounding box to the contour
            (x, y, w, h) = cv2.boundingRect(c)
            sx = int(scale * x)
            sy = int(scale * y)
            sw = int(scale * w)
            sh = int(scale * h)

            if x + w > sRight:
                if self.debug:
                    cv2.rectangle(copy, (sx, sy), (sx + sw, sy + sh), colors.CYAN)
                continue
            if x < sLeft:
                if self.debug:
                    cv2.rectangle(copy, (sx, sy), (sx + sw, sy + sh), colors.CYAN)
                continue
            if y < sTop:
                if self.debug:
                    cv2.rectangle(copy, (sx, sy), (sx + sw, sy + sh), colors.CYAN)
                continue
            if y + h > sBottom:
                if self.debug:
                    cv2.rectangle(copy, (sx, sy), (sx + sw, sy + sh), colors.CYAN)
                continue
            if (w >= sMindiff or h >= sMindiff) and w < width and h < height:
                copy = get_copy(copy)
                if self.debug or self.show_motion:
                    cv2.rectangle(copy, (sx, sy), (sx + sw, sy + sh), colors.GREEN)
                motion_data.motion_detected = True
            else:
                if self.debug:
                    copy = get_copy(copy)
                    cv2.rectangle(copy, (sx, sy), (sx + sw, sy + sh), colors.MAGENTA)

        motion_data._motion_image = copy
        return motion_data
