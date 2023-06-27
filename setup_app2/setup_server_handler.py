import logging
import os.path
from http import server
from jinja2 import Environment, FileSystemLoader
import platform
from picamera2 import Picamera2

FILE_DIR = os.path.dirname(os.path.abspath(__file__))


class SetupServerHandler(server.BaseHTTPRequestHandler):
    TEMPLATE_DIR = os.path.join(FILE_DIR, 'pages')
    ENVIRONMENT = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

    PICAMERA = Picamera2()

    def __init__(self, request, client_address, server):
        super().__init__(request, client_address, server)
        self._content_directory = os.path.join(FILE_DIR, 'pages')
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

    def load_stream(self):
        pass

    def get_pi_model(self):
        with open('/proc/device-tree/model') as f:
            model:str = f.read()
        if model.endswith('\x00'):
            model = model[:-1]
        return model

    def get_camera_model(self):
        m = self.PICAMERA.global_camera_info()[0]['Model']
        known = {
            'ov5647': 'V1',
            'imx219': 'V2',
            'imx477': 'HQ',
            'imx708_wide': 'V3-wide'
        }
        if m in known:
            return known[m]
        return m

    def do_GET(self):
        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/index.html')
            self.end_headers()
        elif self.path == '/index.html':
            path = self.path[1:] if self.path.startswith('/') else self.path
            # [{'Model': 'imx708_wide', 'Location': 2, 'Rotation': 180, 'Id': '/base/soc/i2c0mux/i2c@1/imx708@1a'}]
            self.render_page(os.path.basename(path),
                             hostname=platform.node(),
                             sensor_modes=self.PICAMERA.sensor_modes,
                             camera_model=self.get_camera_model(),
                             pi_model=self.get_pi_model()
                             )
        elif self.path == '/stream.mjpg':
            self.load_stream()
        else:
            self.send_error(404)
            self.end_headers()
