#!/usr/bin/env python3
import argparse
from datetime import datetime

import sqlalchemy
from sqlalchemy.ext.declarative import declarative_base
import sqlalchemy.types as types
from sqlalchemy.orm import sessionmaker

class TZDateTime(types.TypeDecorator):
    impl = sqlalchemy.DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        # if value is not None:
        # if not value.tzinfo:
        #     raise TypeError("tzinfo is required")
        # value = value.astimezone(timezone.utc).replace(
        #     tzinfo=None
        # )
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            # value = value.replace(tzinfo=timezone.utc)
            value = value.astimezone()
        return value

Base = declarative_base()

TABLE_NAME = 'camera_settings'
class CameraSettingsData(Base):
    __tablename__ = 'camera_settings'
    id = sqlalchemy.Column(sqlalchemy.INTEGER, primary_key=True, autoincrement=True)
    timestamp = sqlalchemy.Column('timestamp', TZDateTime)
    shutter_speed = sqlalchemy.Column('shutter_speed', sqlalchemy.Float)
    iso = sqlalchemy.Column('iso', sqlalchemy.Integer)
    aperture = sqlalchemy.Column('aperture', sqlalchemy.Float)
    awb_mode = sqlalchemy.Column('awb_mode', sqlalchemy.String)
    meter_mode = sqlalchemy.Column('meter_mode', sqlalchemy.String)
    exposure_mode = sqlalchemy.Column('exposure_mode', sqlalchemy.String)
    analog_gain = sqlalchemy.Column('analog_gain', sqlalchemy.Float)
    digital_gain = sqlalchemy.Column('digital_gain', sqlalchemy.Float)
    lux = sqlalchemy.Column('lux', sqlalchemy.Float)
    camera_model = sqlalchemy.Column('camera_model', sqlalchemy.String)
    app_name = sqlalchemy.Column('app_name', sqlalchemy.String)
    pi_model = sqlalchemy.Column('pi_model', sqlalchemy.String)
    hostname = sqlalchemy.Column('hostname', sqlalchemy.String)

class CameraSettingsDatabase:
    MAX_COMMIT = 10000 # maximum number of records in single commit
    def __init__(self):
        self.db_path = None
        self.db_engine = None

    def open_database(self, path, echo=False):
        self.db_path = path
        print(f'Opening DB: {self.db_path}')
        uri = f'sqlite:///{self.db_path}'
        print(uri)
        self.db_engine = sqlalchemy.create_engine(uri, echo = echo)
        self.metadata = Base.metadata # sqlalchemy.MetaData(self.db_engine)
        Base.metadata.create_all(self.db_engine)
        self.db_engine.connect()
        print('database open')
        return self.db_engine

    def _open_session(self):
        if not self.db_engine:
            return None
        Session = sessionmaker(bind = self.db_engine)
        return Session()

    def insert_records(self, records, callback=None):
        with self._open_session() as session:
            count = 0
            for record in records:
                session.add(record)
                count += 1
                if count % self.MAX_COMMIT == 0:
                    print(f' - Committing {count} records...')
                    session.commit()
                    if callback:
                        callback(count)
            if count > 0:
                print(f' - Committing {count} records...')
                session.commit()
                if callback:
                    callback(count)

def parse_command_line():
    parser = argparse.ArgumentParser('Import camera settings data into sqlite database')
    parser.add_argument('--db', type=str, required=True,
                        help='Path to database. Will be created or added to.')
    parser.add_argument('--input', type=str, required=True,
                        help='path to csv file of camera settings data')

    return parser.parse_args()

if __name__ == '__main__':
    config = parse_command_line()
    db = CameraSettingsDatabase()
    db.open_database(config.db)

    records = []

    def make_datetime(datetime_string):
        format = '%Y/%m/%d %H:%M:%S.%f'
        d = datetime.strptime(datetime_string, format)
        return d

    with open(config.input) as f:
        for line in f.readlines():
            record_in = line.split(',')
            nfields = len(record_in)
            record_out = CameraSettingsData(
                timestamp = make_datetime(record_in[0]),
                shutter_speed = record_in[1],
                iso = record_in[2],
                aperture = record_in[3],
                awb_mode = record_in[4],
                meter_mode = record_in[5],
                exposure_mode = record_in[6],
                analog_gain = record_in[7],
                digital_gain = record_in[8],
                lux = record_in[9],
                camera_model = record_in[10] if nfields > 10 else '',
                app_name = record_in[11] if nfields > 11 else '',
                pi_model = record_in[12] if nfields > 12 else '',
                hostname = record_in[13] if nfields > 13 else ''
            )
            records.append(record_out)
    db.insert_records(records)