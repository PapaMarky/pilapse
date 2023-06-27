import logging
import socketserver
from http import server


class WebServer(socketserver.ThreadingMixIn, server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, handler, address='', port=8080):
        super().__init__((address, port), handler)



