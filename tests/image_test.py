import logging

import cv2
import os
import logging
import unittest

from pilapse.threads import FileImage, CameraImage

THIS_DIR = os.path.dirname(os.path.abspath(__file__))

testfileprefix = 'picam001'
testfilename = '20230427_223036.698353'
testfilename_re = r'[0-9]'
testfiletype = 'png'
testpath = os.path.join(THIS_DIR, 'data', f'{testfileprefix}_{testfilename}.{testfiletype}')

class TestImages(unittest.TestCase):
    def test_file_image(self):
        file_image = FileImage(testpath)

        self.assertIsNotNone(file_image)
        self.assertEqual(file_image.filepath, testpath)
        self.assertEqual(file_image.timestamp_file, testfilename)
        self.assertEqual(file_image.base_filename, f'{testfileprefix}_{testfilename}')
        self.assertEqual(file_image.filename, f'{testfileprefix}_{testfilename}.{testfiletype}')
        self.assertEqual(file_image.timestamp_human, '2023/04/27 22:30:36')

    def test_camera_image(self):
        image = cv2.imread(testpath)
        cimage = CameraImage(image, prefix=testfileprefix, type=testfiletype)
        self.assertIsNotNone(cimage)
        self.assertRegex(cimage.filename, f'{testfileprefix}_[0-9]{{8}}_[0-9]{{6}}\\.[0-9]*\\.{testfiletype}')
