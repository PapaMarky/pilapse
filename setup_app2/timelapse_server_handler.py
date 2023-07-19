import glob
import json
import logging
import os
import signal
from http import server
from jinja2 import Environment, FileSystemLoader

FILE_DIR = os.path.dirname(os.path.abspath(__file__))


class SetupServerHandler(server.BaseHTTPRequestHandler):
    TEMPLATE_DIR = os.path.join(FILE_DIR, 'tlpages')
    ENVIRONMENT = Environment(loader=FileSystemLoader(TEMPLATE_DIR))
    FRAME_DIR=None
    EXP=None
    PID=None
    CAMERA_INFO = None

    def get_pi_model(self):
        with open('/proc/device-tree/model') as f:
            model:str = f.read()
        if model.endswith('\x00'):
            model = model[:-1]
        return model

    def get_camera_metadata(self):
        return self.PICAMERA.capture_metadata()

    def __init__(self, request, client_address, server):
        super().__init__(request, client_address, server)
        self._content_directory = os.path.join(FILE_DIR, 'tlpages')
        print(f'Content Directory: {self._content_directory}')

    @property
    def content_directory(self):
        return SetupServerHandler.TEMPLATE_DIR

    def render_page(self, page_name, **kwargs):
        template = SetupServerHandler.ENVIRONMENT.get_template(page_name)
        content = template.render(**kwargs).encode('utf-8')

        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.send_header('Content-Length', len(content))
        self.end_headers()
        self.wfile.write(content)

    def load_latest_image(self):
        frame_dir = SetupServerHandler.FRAME_DIR.replace('/home/pi', '')
        path = os.path.join(self.content_directory, SetupServerHandler.FRAME_DIR, '*.jpg')
        print(f'CONTENT: {self.content_directory}')
        print(f'PATH: {path}')
        filelist = glob.glob(path)
        filelist.sort()
        if len(filelist) <= 0:
            self.send_response(200)
            self.send_header('Content-Type', 'text')
            self.end_headers()
            self.wfile.write('No Images'.encode('utf-8'))
            return

        latest = filelist[-1]
        latest = frame_dir + '/' + os.path.basename(latest)
        print(f'LATEST: {latest}')
        self.send_response(200)
        self.send_header('Content-Type', 'text')
        self.end_headers()
        self.wfile.write(latest.encode('utf-8'))

    def send_image(self, path):
        print(f'sending {path}')
        content_path = os.path.join(self.content_directory, path[1:])
        print(f'CONTENT: {content_path}')
        if not os.path.exists(content_path):
            print(f'IMAGE NOT FOUND: {path}')
            self.send_response(404)
            self.send_header('Content-Type', 'text')
            self.end_headers()
            self.wfile.write(f'{path} not found')
        else:
            with open(content_path, 'rb') as img:
                data = img.read()
                l = len(data)
                print(f'LENGTH: {l}')
                self.send_response(200)
                self.send_header('Content-Type', 'image/jpeg')
                self.send_header('Content-Length', l)
                self.end_headers()
                self.wfile.write(data)

    def do_GET(self):
        print(f'Request for {self.path}')
        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/index.html')
            self.end_headers()
        elif self.path == '/index.html':
            path = self.path[1:] if self.path.startswith('/') else self.path
            self.render_page(os.path.basename(path),
                             pid=SetupServerHandler.PID,
                             exposure_time=SetupServerHandler.EXP,
                             pi_model=self.get_pi_model(),
                             camera_info=SetupServerHandler.CAMERA_INFO
                             )
        elif self.path.startswith('/set_exposure'):
            logging.info(f'set_exposure request: {self.path}')
            a = self.path.split('?')[1]
            args = a.split('&')
            logging.info(f'args: {args}')
            for arg in args:
                logging.info(f'arg: {arg}')
                n, v = arg.split('=')
                if n == 'exp':
                    exposure = v
                elif n == 'zoom':
                    zoom = v
                else:
                    raise Exception(f'BAD REQUEST: {self.path}')
            pid = SetupServerHandler.PID
            print(f'New exposure: {exposure} / zoom: {zoom} for pid {pid}')
            if not pid or not exposure or not zoom:
                print('BAD REQUEST')
                self.send_response(400)
            controls = {
                'Zoom': float(zoom),
                'ExposureTime': float(exposure)
            }
            SetupServerHandler.EXP = controls['ExposureTime']
            with open('/home/pi/timelapse_info_helper.json', 'w') as f:
                logging.info(f'controls: {controls}')
                data = json.dumps(controls)
                logging.info(f'data: {data}')
                f.write(data)
                f.write('\n')
            os.kill(int(pid), signal.SIGUSR1)
            # find the latest image and return it
            self.load_latest_image()
        elif self.path.startswith('/exposures'):
            print(f'request for exposure: {self.path}')
            self.send_image(self.path)
        elif self.path == '/get_latest':
            self.load_latest_image()
        elif self.path.startswith('/singleshot'):
            pid = SetupServerHandler.PID
            logging.info(f'Sending SIGUSR2 to {pid}')
            os.kill(int(pid), signal.SIGUSR2)
            self.send_response(200)
            self.send_header('Content-Type', 'text')
            content = 'OK'
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content.encode('utf-8'))

        elif self.path == '/timelapse.css':
            self.send_response(200)
            self.send_header('Content-Type', 'text/css')
            with open(os.path.join(self.content_directory, os.path.basename(self.path))) as f:
                content = f.read()
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content.encode('utf-8'))
        elif self.path == '/timelapse_app.js':
            self.send_response(200)
            self.send_header('Content-Type', 'text/javascript')
            with open(os.path.join(self.content_directory, 'timelapse_app.js')) as f:
                content = f.read()
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content.encode('utf-8'))

