import argparse
import logging
import os
import sys

from setup_server_handler import SetupServerHandler
from web_server import WebServer

APP_DIR = os.path.dirname(os.path.abspath(__file__))

def get_program_name():
    name = os.path.basename(sys.argv[0])
    s = name.split('.')
    if s[-1] == 'py':
        name = '.'.join(s[:-1])
    return name

def parse_arguments():
    parser = argparse.ArgumentParser('Simple WebServer')
    parser.add_argument('--port', type=int, default=8888,
                        help='Port for server to listen on')
    parser.add_argument('--logfile', type=str, default='stdout',
                        help='Path of file to write log to. Set to "stdout" to specify console. Default is "stdout"')
    parser.add_argument('--html', type=str, default='html')
    return parser.parse_args()

def setup_logging(logfile):
    #logfile = os.environ.get('LOGFILE')

    if not logfile:
        logfile = f'{get_program_name()}.log'

    if logfile == 'stdout':
        logfile = None

    logfile_name = logfile if logfile is not None else 'stdout'

    print(f'Logging to {logfile_name}')
    logging.basicConfig(
        filename=logfile,
        level=logging.INFO,
        format='%(asctime)s|%(levelname)s|%(threadName)s|%(message)s'
    )

if __name__ == '__main__':
    config = parse_arguments()
    setup_logging(config.logfile)
    logging.info(f'App Dir: {APP_DIR}')
    logging.info(f'Starting WebServer on port {config.port}')

    server = WebServer(SetupServerHandler, port=config.port)
    server.serve_forever()
