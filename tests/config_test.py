import logging
import os
import unittest

from pilapse.config import Config
from timelapse import TimelapseConfig
from motion import MotionConfig

THIS_DIR = os.path.dirname(os.path.abspath(__file__))

class TestConfig(unittest.TestCase):

    def test_json_load_defaults_motion(self):
        pilapse_config = MotionConfig()
        logging.info('TEST VALID CONFIG (motion)')
        exception = ''
        try:
            default_config = os.path.join(THIS_DIR, 'data/config-motion-default.json')
            pilapse_config.load_from_json(default_config)
            raised = False
        except Exception as e:
            raised = True
            exception = f'{e}'
        self.assertFalse(raised, f'should not throw exception {exception}')

    def test_json_load_defaults_timelapse(self):
        pilapse_config = TimelapseConfig()
        logging.info('TEST VALID CONFIG (timelapse)')
        exception = ''
        try:
            default_config = os.path.join(THIS_DIR, 'data/config-timelapse-default.json')
            pilapse_config.load_from_json(default_config)
            raised = False
        except Exception as e:
            raised = True
            exception = f'{e}'
        self.assertFalse(raised, f'should not throw exception {exception}')

    def test_json_load_missing(self):
        pilapse_config = Config()
        with self.assertRaises(Exception) as context:
            pilapse_config.load_from_json('xxx')
        assert isinstance(context.exception, FileNotFoundError)

if __name__ == '__main__':
    unittest.main()