import argparse
import json
import logging
import os
import sys

class Config():

    def __init__(self):
        self._version = '1.0'

    def get_defaults(self):
        parser = self.create_parser()
        config = self.load_from_list()
        return config

    def dump_to_log(self, config):
        logging.info('-- START CONFIG DUMP --')
        if config is None:
            logging.error(' - Bad Config')
        else:
            for attr, value in config.__dict__.items():
                logging.info(f'{attr:>15}: {value}')
        logging.info('-- END CONFIG DUMP --')

    def dump_to_json(self, filename='config.json', indent=0, arglist=None):
        logging.info(f'Dumping config to json: {filename}..')
        config = self.load_from_list(arglist)

        if 'save-config' in config.__dict__:
            config.__dict__.pop('save-config')
        with open(filename, 'w') as json_file:
            json_file.write(json.dumps(config.__dict__, indent=indent))

    def clean_for_export(self, config:argparse.Namespace):
        pass


    def load_from_json(self, filename):
        try:
            with open(filename) as json_file:
                new_config = json.load(json_file)

                # validate the newly loaded config
                default_config = self.get_defaults()

                logging.info(f'DEF CONFIG: {default_config}')
                logging.info(f'NEW CONFIG: {new_config}')

                for key, value in default_config.__dict__.items():
                    if not key in new_config:
                        raise Exception(f'Parameter Not Found in config: {key}')
                    logging.info(f'{key:15}: {value}')
                    #mstring = "MATCH" if value == new_config[key] else "NOT MATCHING"
                    logging.info(f'{"":15}  {str(new_config[key]):20}')
                    logging.info(f'--------------')
        except Exception as e:
            logging.exception(f'Exception loading {filename}')
            raise e

    def load_from_list(self, arglist=None):
        parser = self.create_parser()
        namespace = argparse.Namespace()
        config = parser.parse_args(args=arglist, namespace=namespace)
        config.version = self._version
        return config

    def create_parser(self):
        raise Exception('Not implemented in base class')

    def get_config(self):
        return(self.config)
