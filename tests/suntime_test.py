import datetime
import json
import os
import sys
import unittest
from suntime import Suntime, parse_time
import logging

SHOW_LOGS=False
if SHOW_LOGS:
    logger = logging.getLogger()
    logger.level = logging.DEBUG

THIS_DIR = os.path.dirname(os.path.abspath(__file__))

# URL TO GENERATE TEST DATA:
#
location = (37.335480, -121.893028)
date = '2023-06-18'
testpath = os.path.join(THIS_DIR, 'data', f'{date}_suntime.json')
testdata = json.load(open(testpath))
testdate = datetime.datetime(2023, 6, 18)

class TestSuntime(unittest.TestCase):
    def test_value_from_name(self):
        if SHOW_LOGS:
            stream_handler = logging.StreamHandler(sys.stdout)
            logger.addHandler(stream_handler)
        suntime = Suntime(location, date=date)

        for name in suntime.valid_times():
            value = suntime.value_from_name(name)
            self.assertIsNotNone(value)

            self.assertEqual(parse_time(testdata['results'][name], testdate) , value)