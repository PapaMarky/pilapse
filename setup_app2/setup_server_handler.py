import logging
import os.path
from http import server
from jinja2 import Environment, FileSystemLoader
import platform
from picamera2 import Picamera2
from threading import Condition

FILE_DIR = os.path.dirname(os.path.abspath(__file__))


class SetupServerHandler(server.BaseHTTPRequestHandler):
    TEMPLATE_DIR = os.path.join(FILE_DIR, 'pages')
    ENVIRONMENT = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

    PICAMERA = None
    SENSOR_MODES = {}
    OUTPUT = None
    ASPECT_RATIO = '4:3'
    SCALAR_CROP_BASE=None
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
        if SetupServerHandler.OUTPUT is None:
            self.send_response(204) # no content
            return
        self.send_response(200)
        self.send_header('Age', 0)
        self.send_header('Cache-Control', 'no-cache, private')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
        self.end_headers()
        try:
            while True:
                with SetupServerHandler.OUTPUT.condition:
                    SetupServerHandler.OUTPUT.condition.wait()
                    frame = SetupServerHandler.OUTPUT.frame
                self.wfile.write(b'--FRAME\r\n')
                self.send_header('Content-Type', 'image/jpeg')
                self.send_header('Content-Length', len(frame))
                self.end_headers()
                self.wfile.write(frame)
                self.wfile.write(b'\r\n')
        except Exception as e:
            logging.warning(
                'Removed streaming client %s: %s',
                self.client_address, str(e))

    def get_pi_model(self):
        with open('/proc/device-tree/model') as f:
            model:str = f.read()
        if model.endswith('\x00'):
            model = model[:-1]
        return model

    def get_camera_metadata(self):
        return self.PICAMERA.capture_metadata()

    def get_camera_model(self):
        if SetupServerHandler.PICAMERA is None:
            return 'None'
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
    def get_sensor_modes(self):
        if SetupServerHandler.PICAMERA is None:
            return {}
        return SetupServerHandler.SENSOR_MODES

    def set_zoom(self):
        x = self.path.split('?')
        zoom = int(x[1].split('=')[1])
        logging.info(f'set zoom: {zoom}')
        metadata = self.get_camera_metadata()
        if SetupServerHandler.SCALAR_CROP_BASE is None:
            SetupServerHandler.SCALAR_CROP_BASE = metadata['ScalerCrop']
        x, y, w, h = SetupServerHandler.SCALAR_CROP_BASE
        new_w = w/zoom
        new_h = h/zoom
        new_x = x + w/2 - new_w/2
        new_y = y + h/2 - new_h/2
        controls = {'ScalerCrop': (int(new_x), int(new_y), int(new_w), int(new_h))}
        self.PICAMERA.set_controls(controls)

    def do_GET(self):
        print(f'Request for {self.path}')
        print(f'PICAMERA: {self.PICAMERA}')
        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/index.html')
            self.end_headers()
        elif self.path == '/index.html':
            path = self.path[1:] if self.path.startswith('/') else self.path
            # [{'Model': 'imx708_wide', 'Location': 2, 'Rotation': 180, 'Id': '/base/soc/i2c0mux/i2c@1/imx708@1a'}]
            metadata = self.get_camera_metadata()
            print(f'ExposureTime: {metadata["ExposureTime"]}')
            if SetupServerHandler.ASPECT_RATIO == '6:4':
                img_w = 640
                img_h = 480
            else:
                img_w= 1920 * 0.75
                img_h = 1080 * 0.75
            self.render_page(os.path.basename(path),
                             hostname=platform.node(),
                             sensor_modes=self.get_sensor_modes(),
                             camera_model=self.get_camera_model(),
                             pi_model=self.get_pi_model(),
                             exposure_time=metadata['ExposureTime'],
                             img_w=img_w,
                             img_h=img_h,
                             )
        elif self.path == '/stream.mjpg':
            self.load_stream()
        elif self.path.startswith('/set_zoom?'):
            self.set_zoom()
        elif self.path == '/setup_app.js':
            self.send_response(200)
            self.send_header('Content-Type', 'text/javascript')
            with open(os.path.join(self.content_directory, 'setup_app.js')) as f:
                content = f.read()
            self.send_header('Content-Length', len(content))
            self.end_headers()
            self.wfile.write(content.encode('utf-8'))
        elif self.path.startswith('/set_control?'):
            a = self.path.split('?')[1]
            args = a.split('&')
            for arg in args:
                n, v = arg.split('=')
                if n == 'name':
                    name = v
                elif n == 'value':
                    value = v
                else:
                    raise Exception(f'BAD REQUEST: {self.path}')
            controls = {name: int(value)}
            self.PICAMERA.set_controls(controls)
            self.send_response(200)
            self.send_header('Content-Type', 'text')
            self.end_headers()
            self.wfile.write('OK'.encode('utf-8'))
            metadata = self.get_camera_metadata()
            for m in metadata:
                print(f'{m}: {metadata[m]}')
        else:
            print(f'BAD REQUEST: {self.path}')
            self.send_error(404)
            self.end_headers()
