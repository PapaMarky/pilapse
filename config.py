import argparse
import json
import logging
import sys


class Config():


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


    def create_parser(self):
        raise Exception('Not implemented in base class')

    def get_config(self):
        return(self.config)

class Configurable:
    PARAM_LIST = {

    }

    ARGS_ADDED = False
    @classmethod
    def create_parser(cls, description=None):
        parser = argparse.ArgumentParser(description=description)
        return parser


    @classmethod
    def add_arguments_to_parser(cls, parser:argparse.ArgumentParser, argument_group_name:str= 'Application Settings')->argparse.ArgumentParser:
        logging.debug(f'Adding Config({cls}) args to parser (ADDED: {Configurable.ARGS_ADDED})')
        configuration = parser.add_argument_group(argument_group_name, 'Parameters related to the configuration')
        configuration.add_argument('--loglevel', type=str,
                             help='Set the log level.')
        configuration.add_argument('--save-config', action='store_true', help='Save config to jsonfile and exit.')
        configuration.add_argument('--debug', action="store_true",
                               help='Turn on debugging')

        return parser

    @classmethod
    def validate_config(cls, config):
        if config.loglevel is not None:
            oldlevel = logging.getLevelName(logging.getLogger().getEffectiveLevel())
            level = config.loglevel.upper()
            logging.info(f'Setting log level from {oldlevel} to {level}')
            logging.getLogger().setLevel(level)

    def __init__(self):
        self._version = '1.0'
        self._parser:argparse.ArgumentParser = None

    def get_defaults(self):
        self._parser = self.create_parser()
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

    def load_from_list(self, parser, arglist=None):
        namespace = argparse.Namespace()
        config = parser.parse_args(args=arglist, namespace=namespace)
        config.version = self._version
        Configurable.validate_config(config)

        return config


    def process_config(self, config):
        logging.info('Config process_config')
        if config.save_config:
            config_file = 'motion-config.json'
            logging.info(f'Saving config to {config_file}')
            config.save_config = False
            with open(config_file, 'w') as json_file:
                logging.info(f'Dict Type: {type(config.__dict__)}')
                logging.info(f'Dict: {config.__dict__}')
                json_file.write(json.dumps(config.__dict__, indent=2))
            sys.exit()
