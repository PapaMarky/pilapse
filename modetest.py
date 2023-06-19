import argparse
import logging
import threading

from pilapse.camera_producer import CameraProducer
from pilapse.config import Configurable
from pilapse.scheduling import Schedule
from pilapse.threads import ImageWriter, ImageProducer, CameraImage
import pilapse as pl
from queue import Queue
from picamera import PiCamera

class ModeTestCameraProducer(CameraProducer):
    ARGS_ADDED = False
    @classmethod
    def add_arguments_to_parser(cls, parser:argparse.ArgumentParser, argument_group_name:str= 'Camera Settings')->argparse.ArgumentParser:
        logging.info(f'Adding {cls.__name__} args to parser (ADDED:{cls.ARGS_ADDED})')
        if cls.ARGS_ADDED:
            return parser
        CameraProducer.add_arguments_to_parser(parser, argument_group_name)
        parser.add_argument('--ignore-exposure', type=str,
                            help='comma separated list of exposure modes to ignore')
        parser.add_argument('--exposure-list', type=str,
                            help='comma separated list of exposure modes to include')
        parser.add_argument('--ignore-awb', type=str,
                            help='comma separated list of awb modes to ignore')
        parser.add_argument('--awb-list', type=str,
                            help='comma separated list of awb modes to include')
        parser.add_argument('--modepause', type=float, default=1.0,
                            help='Number of seconds to pause between setting up camera and capturing image')

    def __init__(self,
                 shutdown_event:threading.Event, config:argparse.Namespace,
                 **kwargs):
        super().__init__(shutdown_event, config, **kwargs)
        self.ignore_exposure_list = []
        self.exposure_list = []
        self.ignore_awb_list = []
        self.awb_list = []

        if self.config.ignore_exposure and self.config.exposure_list:
            logging.error('Setting both --ignore-exposure and --exposure-list is not allowed')
            self.shutdown_event.set()
        if self.config.ignore_exposure and self.config.exposure_list:
            logging.error('Setting both --ignore-awb and --awb-list is not allowed')
            self.shutdown_event.set()

        if self.config.ignore_exposure:
            self.ignore_exposure_list = self.config.ignore_exposure.split(',')
        if self.config.ignore_awb:
            self.ignore_awb_list = self.config.ignore_awb.split(',')

        if self.config.exposure_list:
            self.exposure_list = self.config.exposure_list.split(',')
        else:
            self.exposure_list = PiCamera.EXPOSURE_MODES

        if self.config.awb_list:
            self.awb_list = self.config.awb_list.split(',')
        else:
            self.awb_list = PiCamera.AWB_MODES


    def preproduce(self):
        return True

    def produce_image(self) -> str:
        for exposure_mode in self.exposure_list:
            if exposure_mode == 'off' or exposure_mode in self.ignore_exposure_list:
                continue
            for awb_mode in self.awb_list:
                if awb_mode == 'off' or awb_mode in self.ignore_awb_list:
                    continue
                if self.shutdown_event.is_set():
                    return
                logging.info(f'Testing Image: exp: {exposure_mode}, awb: {awb_mode}')
                self.camera.picamera.exposure_mode = exposure_mode
                self.camera.picamera.awb_mode = awb_mode
                self.shutdown_event.wait(self.config.modepause)
                img = CameraImage(self.camera.capture(), prefix=f'{exposure_mode}_{awb_mode}', type='jpg')
                lux = self.light_meter.lux if self.light_meter.available else None
                awb_gains = self.camera.picamera.awb_gains
                awb_gains = (float(awb_gains[0]), float(awb_gains[1]))
                img.set_camera_data(self.camera.picamera.exposure_speed/1000000,
                                    self.camera.picamera.ISO,
                                    self.aperture,
                                    self.camera.picamera.awb_mode,
                                    self.camera.picamera.meter_mode,
                                    self.camera.picamera.exposure_mode,
                                    float(self.camera.picamera.analog_gain),
                                    float(self.camera.picamera.digital_gain),
                                    awb_gains,
                                    lux)

                logging.debug(f'captured {img.base_filename}')
                self.add_to_out_queue(img)

        self.shutdown_event.set()

class ModeTestApp(Configurable):

    ARGS_ADDED = False
    @classmethod
    def add_arguments_to_parser(cls, parser:argparse.ArgumentParser, argument_group_name:str='Picamera Mode Test Settings')->argparse.ArgumentParser:
        ModeTestCameraProducer.add_arguments_to_parser(parser)
        ImageWriter.add_arguments_to_parser(parser)

        return parser

    def __init__(self):
        self._version = '1.0.0'
        self._camera_producer:ModeTestCameraProducer = None
        self._image_writer:ImageWriter = None

        parser = Configurable.create_parser('Timelapse App for Raspberry Pi')
        self._parser = ModeTestApp.add_arguments_to_parser(parser)
        self._config = self.load_from_list(self._parser)
        ModeTestApp.validate_config(self._config)


        if not pl.it_is_time_to_die():
            self.process_config(self._config)
            self.out_queue = Queue()
            self._shutdown_event = threading.Event()

    def run(self):
        if pl.it_is_time_to_die():
            return
        ###
        # Create a Motion Consumer and Image Producer. Start them up.

        producer = None
        # create images using camera
        producer = ModeTestCameraProducer(self._shutdown_event, self._config, out_queue=self.out_queue)
        writer = ImageWriter(self._shutdown_event, self._config, in_queue=self.out_queue)

        writer.start()
        producer.start()

        while True:
            logging.debug(f'waiting: producer alive? {producer.is_alive()},  writer alive? {writer.is_alive()}')
            if not producer.is_alive() or not writer.is_alive():
                self._shutdown_event.set()
                pl.set_time_to_die()

            if pl.it_is_time_to_die():
                logging.info('Shutting down')
                self._shutdown_event.set()
                break

                logging.info('Waiting for producer...')
                try:
                    producer.join(5.0)
                    if producer.is_alive():
                        logging.warning('- Timed out, producer is still alive.')
                except Exception as e:
                    logging.exception(e)

                logging.info('Waiting for writer...')
                try:
                    writer.join(5.0)
                    if writer.is_alive():
                        logging.warning('- Timed out, writer is still alive.')
                except Exception as e:
                    logging.exception(e)

                break
            self._shutdown_event.wait(1)
            if self._shutdown_event.is_set():
                pl.set_time_to_die()
                break
        pl.die()

def main():
    try:
        if not pl.create_pid_file():
            pl.die()
        app = ModeTestApp()
        if not pl.it_is_time_to_die():
            app.run()
    except Exception as e:
        logging.exception('Exception in Main')
        logging.exception(e)
        pl.die(1)

if __name__ == '__main__':
    try:
        main()
        if pl.it_is_time_to_die():
            logging.info('Exiting: Graceful shutdown')
    except Exception as e:
        logging.exception(f'Unhandled Exception: {e}')
        pl.die(1)