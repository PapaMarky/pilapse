import argparse
import logging
import os
import shutil
import sys
from pathlib import Path
from data_scaler import DataScaler
import cv2

logging.basicConfig(level=logging.INFO, stream=sys.stdout, format='%(asctime)s|%(levelname)s|%(threadName)s|%(message)s')

def parse_args():
    parser = argparse.ArgumentParser('Postprocess Motion Detection Video Clips')
    parser.add_argument('work_dir', help='path to work dir. (Directory containing "raw")', type=Path)
    return parser.parse_args()

class ClipMetadata(object):
    def __init__(self, path:Path):
        self.header = {}
        self.framedata = []
        self.load(path)

    @property
    def version(self):
        return self.header['version'] if 'version' in self.header else None

    @property
    def nframes(self):
        return len(self.framedata)

    @property
    def fps(self):
        return self.header['fps'] if 'fps' in self.header else None

    def get_frame(self, i):
        if i < 0 or i >= len(self.framedata):
            message = f'bad frame index: {i} is not between 0 and {len(self.framedata)}'
            logging.error(message)
            return None
        return self.framedata[i]

    def parse_header(self, header:str):
        self.header = {}
        if header.startswith('CLIP: '):
            header = header[6:]
            fields = header.split(',')
            for field in fields:
                field = field.strip()
                x = field.split(':')
                self.header[x[0].strip()] = x[1].strip()

        logging.info(f'HEADER: {self.header}')

    def load_framedata(self, content):
        self.framedata = []
        n = 0
        for frame in content:
            fields = frame.split(',')
            self.framedata.append(
                {
                    'timestamp': fields[0],
                    'fps': fields[1],
                    'lux': fields[2],
                    'mse': fields[3],
                    'ave_mse': fields[4],
                    'motion': fields[5] == 'M'
                }
            )
            n += 1
        logging.info(f'Collected {n} frames worth of data')

    def load(self, path:Path):
        logging.info(f'Load metadata from {path.name}')
        self.header = {}
        self.framedata = []
        content = path.read_text('utf-8').splitlines()
        header = content.pop(0)
        self.parse_header(header)
        self.load_framedata(content)

RED = (0, 0, 255)
GREEN = (0, 255, 0)
BLUE = (255, 0, 0)
YELLOW = (0, 255, 255)
TURQUOIS = (255, 255, 0)
MAGENTA = (255, 0, 255)
class RawClipProcessor(object):
    DEFAULT_FPS = 30
    bottom_margin = 10
    def __init__(self, raw_clip_path:Path, outdir:Path):
        self.fps = None
        self.motion_graph = None
        self.mse_average_graph = None
        self.delta_graph = None
        self.title_frame_number = None
        self.clip_path:Path = raw_clip_path
        self.outdir:Path = outdir
        logging.info(f'Process {self.clip_path.name}')
        self.clip_base_name = raw_clip_path.with_suffix('').name
        self.clip_timestamp = self.clip_base_name.split('_')[0]
        self.work_dir:Path = raw_clip_path.parent
        self.temp_dir:Path = self.work_dir.joinpath('tmp', self.clip_base_name)
        self.temp_dir.mkdir(exist_ok=True, parents=True)
        metadata_list = []
        for f in self.work_dir.glob(f'{self.clip_timestamp}*_data.txt'):
            metadata_list.append(f)
        if len(metadata_list) < 1:
            raise Exception('Metadata file not found')
        if len(metadata_list) > 1:
            raise Exception(f'Too many metadata files found for {raw_clip_path.name}')
        self.metadata_path = metadata_list[0]
        self.metadata = ClipMetadata(self.metadata_path)

    def frame_file_path(self, index):
        return f'{self.temp_dir}/frame_{index:06}.png'
    def split_clip(self):
        logging.info(f'Splitting {self.clip_path.name} into Frames')
        # pass one, pull out frames, numbering frame00000, frame00001, etc
        video_capture = cv2.VideoCapture(str(self.clip_path))
        # TODO check first frame fps, last frame fps and clip fps. 2 out of 3 wins
        self.fps = int(self.metadata.fps)
        logging.info(f'No FPS in metadata, checking first and last frames.')
        fps_data = {}
        for frame in self.metadata.framedata:
            fps = frame['fps']
            if fps not in fps_data:
                fps_data[fps] = 0
            fps_data[fps] += 1

        logging.info(f'--- FPS DATA ---')
        clip_fps = None
        for k,v in fps_data.items():
            logging.info(f' {k}: {v}')
            if clip_fps is None:
                clip_fps = k
            else:
                if v > fps_data[clip_fps]:
                    clip_fps = k
        logging.info(f' - clip_fps: {clip_fps}')

        self.fps = int(clip_fps)
        self.frame_width = int(video_capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_height = int(video_capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.frame_count = 0

        while True:
            success, frame = video_capture.read()
            if not success:
                break
            cv2.imwrite(self.frame_file_path(self.frame_count), frame)
            self.frame_count += 1
        video_capture.release()
        logging.info(f'Wrote {self.frame_count} frames to {self.temp_dir.name}')
        # now we know how many frames, we can map to metadata

    def calculate_motion_graph(self):
        view_x_limits = [0, self.frame_width - 1]
        view_y_limits = [self.frame_height - 1 - self.bottom_margin, self.frame_height - self.frame_height/10 - self.bottom_margin]

        max_mse = min_mse = None

        metadata_offset = self.metadata.nframes - self.frame_count
        if self.metadata.nframes > self.frame_count:
            metadata_offset -= 1
        if self.metadata.nframes < self.frame_count:
            metadata_offset = 0
        logging.debug(f'Calculate motion graph: {self.metadata.nframes} metadata frames, {self.frame_count} '
                     f'frames, offset: {metadata_offset}')
        self.motion_graph = []
        self.mse_average_graph = []
        self.mse_line = []
        self.delta_graph = []
        motion_data = []
        mse_average_data = []
        delta_data = []
        for i in range(self.frame_count):
            try:
                metadata_frame = self.metadata.get_frame(metadata_offset + i)
            except Exception as e:
                logging.error(f'Failed to get metadata for frame {i}')
                logging.error(f'{self.metadata.nframes} metadata frames, {self.frame_count} frames, offset:')
                raise e
            mse_threshold = float(self.metadata.header['mse'])
            mse = float(metadata_frame['mse']) if metadata_frame is not None else 0
            motion_data.append(mse)
            ave = float(metadata_frame['ave_mse']) if metadata_frame is not None else 0
            mse_average_data.append(ave)
            delta = float(abs(mse - ave))
            delta_data.append(delta)
            if i == 0:
                min_mse = max_mse = mse
                continue
            if mse < min_mse:
                min_mse = mse
            if mse > max_mse:
                max_mse = mse
                self.title_frame_number = i
            if ave < min_mse:
                min_mse = ave
            if ave > max_mse:
                max_mse = ave

        self.xscaler = DataScaler([0, self.frame_count - 1], view_x_limits)
        # self.yscaler = DataScaler([0, max(max_mse, mse_threshold * 2.0)], view_y_limits)
        self.yscaler = DataScaler([0, mse_threshold * 2.0], view_y_limits)

        Y = int(self.yscaler.scale(mse_threshold))
        self.mse_line = [(view_x_limits[0], Y), (view_x_limits[1], Y)]

        for i in range(self.frame_count):
            x = int(self.xscaler.scale(i))

            y = int(self.yscaler.scale(motion_data[i]))
            self.motion_graph.append((x, y))

            y = int(self.yscaler.scale(mse_average_data[i]))
            self.mse_average_graph.append((x, y))

            y = int(self.yscaler.scale(delta_data[i]))
            self.delta_graph.append((x, y))

    def create_raw_video(self):
        clip_dir = self.temp_dir.parent
        discard = ''
        if 'discard' in str(self.clip_path):
            discard = '_DISCARD'
        clip_name = clip_dir.joinpath(f'{self.clip_base_name}{discard}.mp4')
        logging.info(f'video output dir: {clip_dir}, clip fps: {self.fps}')
        frame_files = self.temp_dir.glob('frame_*.png')

        size = (self.frame_width, self.frame_height)
        fourcc = cv2.VideoWriter_fourcc('m', 'p', '4', 'v')
        video_writer = cv2.VideoWriter()
        video_writer.open(str(clip_name), fourcc, int(self.fps), size)
        frame_file_list = []
        for frame in frame_files:
            frame_file_list.append(frame)
        frame_file_list.sort()
        title_frame = None
        if self.title_frame_number is not None:
            title_frame = cv2.imread(self.frame_file_path(self.title_frame_number))

        metadata_offset = self.metadata.nframes - self.frame_count
        if self.metadata.nframes > self.frame_count:
            metadata_offset -= 1
        def draw_footer(frame_image, frame_number):

            metadata_frame = self.metadata.get_frame(metadata_offset + frame_number)
            ts = metadata_frame['timestamp'] if metadata_frame is not None else '0000/00/ 00:00:00'
            if self.motion_graph is not None and self.mse_average_graph is not None:
                cursor_x = int(self.xscaler.scale(frame_number))
                cursor_y0 = int(self.yscaler.view_min)
                cursor_y1 = int(self.yscaler.view_max)
                cv2.line(frame_image, (cursor_x, cursor_y0), (cursor_x, cursor_y1), (255, 0, 0), thickness=2)

                def draw_graph(graph, color):
                    previous_point = None
                    for point in graph:
                        if previous_point is not None:
                            cv2.line(frame_image, previous_point, point, color, thickness=2)
                        previous_point = point

                draw_graph(self.mse_line, YELLOW)
                draw_graph(self.mse_average_graph, GREEN)
                draw_graph(self.motion_graph, BLUE)
                draw_graph(self.delta_graph, TURQUOIS)

            mse = float(metadata_frame["mse"]) if metadata_frame is not None else 0
            average = float(metadata_frame["ave_mse"]) if metadata_frame is not None else 0
            message = f'{ts} m{mse:.2f} a{average:.2f} d{abs(mse - average):.2f} fps{self.fps:.0f} {discard}'
            cv2.putText(frame_image, message, timestamp_origin, cv2.FONT_HERSHEY_SIMPLEX, 1, RED, thickness=2)

        frame_number = 0
        timestamp_origin = (30, self.frame_height - 60)
        for frame in frame_file_list:
            if title_frame is not None:
                draw_footer(title_frame, self.title_frame_number)
                video_writer.write(title_frame)
                title_frame = None
            logging.debug(f'Adding frame {frame.name}')
            frame_image = cv2.imread(str(frame))
            # add the timestamp from metadate at the bottom for debugging

            draw_footer(frame_image, frame_number)
            video_writer.write(frame_image)
            frame_number += 1
        video_writer.release()
        # move the file from clip_dir to clip_dir.parent
        shutil.move(clip_name, self.outdir)
        logging.info(f' - Finished writing {clip_name}')

    def cleanup(self):
        logging.info(f'Deleting {self.temp_dir}')
        shutil.rmtree(self.temp_dir)
        # delete the raw video?
        logging.info(f'Deleting {self.clip_path}')
        self.clip_path.unlink()
        # logging.info(f'Deleteing {self.metadata_path}')
        # self.metadata_path.unlink()


def process_raw_clips(raw_path):
    logging.info(f'raw_path type: {type(raw_path)}')
    outdir = raw_path.parent
    raw_clip_list = []
    raw_clip_list.extend(raw_path.glob('*.h264'))
    raw_clip_list.extend(raw_path.joinpath('discards').glob('*.h264'))
    raw_clip_list.sort()
    logging.info(f'Found {len(raw_clip_list)} clips')
    logging.info(f'Motion Post Processing, work dir: {args.work_dir}')
    for raw_clip in raw_clip_list:
        raw_clip_path = os.path.join(raw_path, raw_clip)
        processor = RawClipProcessor(raw_clip, outdir)
        processor.split_clip()
        processor.calculate_motion_graph()
        processor.create_raw_video()
        processor.cleanup()

if __name__ == '__main__':
    args = parse_args()
    raw_path = Path(f'{args.work_dir}/raw/')
    process_raw_clips(raw_path)

