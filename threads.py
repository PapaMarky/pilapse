
import threading
from queue import Queue
import logging

import time

image_queue = Queue()

quit_command = '%quit%'
class ImageProducer(threading.Thread):
    def __init__(self, config):
        super().__init__()

    def run(self) -> None:
        while True:
            image = self.produce_image()
            if image is not None:
                image_queue.put(image)

    def produce_image(self) -> str:
        return quit_command

from picamera import PiCamera
class CameraProducer(ImageProducer):
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.camera = PiCamera()
        logging.info('Setting up camera...')
        self.camera.resolution = (self.config.width, self.config.height)
        self.camera.rotation = 180
        self.camera.framerate = 80
        self.camera.exposure_mode = 'auto'
        self.camera.awb_mode = 'auto'
        # camera.zoom = (0.2, 0.3, 0.5, 0.5)
        time.sleep(2)
        logging.info(f'setup_camera completed: Camera Resolution: {self.camera.MAX_RESOLUTION}')





class ImageConsumer(threading.Thread):
    def __init__(self):
        super().__init__()

    def run(self) -> None:
        while True:
            if not image_queue.empty():
                image = image_queue.get()
                if image == quit_command:
                    return
                self.consume_image(image)

    def consume_image(self, image):
        pass

class MotionConsumer(ImageConsumer):
    def __init__(self):
        super().__init__()
        self.current_image = None
        self.previous_image = None
        self.count = 0

    def consume_image(self, image):
        self.count += 1
        self.previous_image = self.current_image
        self.current_image = image
        if self.previous_image is not None and self.current_image is not None:
            self.compare_images()
    def compare_images(self):
        pass
