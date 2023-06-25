#!/usr/bin/python3
import argparse
# This is the same as mjpeg_server.py, but uses the h/w MJPEG encoder.

import io
import logging
import os
import platform
import socketserver
from http import server
from threading import Condition

from picamera2 import Picamera2
from picamera2.encoders import MJPEGEncoder
from picamera2.outputs import FileOutput
from libcamera import Transform

APP_DIR = os.path.dirname(os.path.abspath(__file__))

parser = argparse.ArgumentParser()
parser.add_argument('--aspect-ratio', '-a', type=str, default='16:9', choices=['4:3', '16:9'],
                    help='aspect ratio  of each frame. ("16:9" or "4:3")')
args = parser.parse_args()
ar_16_9 = [854, 480]
ar_4_3 = [640, 480]
print(args)

frame_width = ar_16_9[0] if args.aspect_ratio == '16:9' else ar_4_3[0]
frame_height = ar_16_9[1] if args.aspect_ratio == '16:9' else ar_4_3[1]
hostname = platform.node()
title = f'{hostname} setup app (Picamera2)'

PAGE = f"""\
<html>
<head>
<title>{hostname} Setup App (Picamera2)</title>
</head>
<body>
<h1>{hostname} Setup App (Picamera2)</h1>
<img src="stream.mjpg" width="{frame_width}" height="{frame_height}" />
</body>
</html>
"""


class StreamingOutput(io.BufferedIOBase):
    def __init__(self):
        self.frame = None
        self.condition = Condition()

    def write(self, buf):
        with self.condition:
            self.frame = buf
            self.condition.notify_all()


class StreamingHandler(server.BaseHTTPRequestHandler):
    INDEX_PAGE = None
    def do_GET(self):
        if self.path == '/':
            self.send_response(301)
            self.send_header('Location', '/index.html')
            self.end_headers()
        elif self.path == '/index.html':
            self.load_index()
        elif self.path == '/stream.mjpg':
            self.load_stream()
        else:
            self.send_error(404)
            self.end_headers()

    def load_page(self, path):
        content = ''
        with open(os.path.join(APP_DIR, path)) as f:
            content = f.read()
            content = content.replace('{width}', str(frame_width)).replace('{height}', str(frame_height))

        return content


    def load_index(self):
        if self.INDEX_PAGE == None:
            self.INDEX_PAGE = self.load_page('pages/index.html')
        content = PAGE.encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.send_header('Content-Length', len(content))
        self.end_headers()
        self.wfile.write(content)

    def load_stream(self):
        self.send_response(200)
        self.send_header('Age', 0)
        self.send_header('Cache-Control', 'no-cache, private')
        self.send_header('Pragma', 'no-cache')
        self.send_header('Content-Type', 'multipart/x-mixed-replace; boundary=FRAME')
        self.end_headers()
        try:
            while True:
                with output.condition:
                    output.condition.wait()
                    frame = output.frame
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

class StreamingServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


picam2 = Picamera2()
transform=Transform(hflip=True, vflip=True)
picam2.configure(picam2.create_video_configuration(main={"size": (frame_width, frame_height)}, transform=transform))
output = StreamingOutput()
picam2.start_recording(MJPEGEncoder(), FileOutput(output))

try:
    address = ('', 8000)
    server = StreamingServer(address, StreamingHandler)
    server.serve_forever()
finally:
    picam2.stop_recording()
