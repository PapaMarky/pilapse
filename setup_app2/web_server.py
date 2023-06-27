import logging
import socketserver
from http import server


class WebServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def call_shutdown(self):
        print(f'Calling shutdown')
        self.shutdown()

    def __init__(self, picam2, handler, address='', port=8080):
        super().__init__((address, port), handler)
        handler.PICAMERA = picam2


