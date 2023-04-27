import logging
import os
import unittest

from pilapse import PilapseConfig

THIS_DIR = os.path.dirname(os.path.abspath(__file__))

class TestConfig(unittest.TestCase):

    def test_json_load_defaults(self):
        pilapse_config = PilapseConfig()
        logging.info('TEST VALID CONFIG')
        exception = ''
        try:
            default_config = os.path.join(THIS_DIR, 'data/config-default.json')
            pilapse_config.load_from_json(default_config)
            raised = False
        except Exception as e:
            raised = True
            exception = f'{e}'
        self.assertFalse(raised, f'should not throw exception {exception}')

    def test_json_load_missing(self):
        pilapse_config = PilapseConfig()
        with self.assertRaises(Exception) as context:
            pilapse_config.load_from_json('xxx')
        assert isinstance(context.exception, FileNotFoundError)

if __name__ == '__main__':
    unittest.main()