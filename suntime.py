import logging
from datetime import datetime, timedelta
from datetime import date
import requests

def parse_time(time_str, day:datetime):
    # logging.info(f'parse time: {time_str}')
    time = datetime.strptime(time_str, '%I:%M:%S %p').time()
    rval = datetime(day.year, day.month, day.day, time.hour, time.minute, time.second)
    return rval

'''
FROM: www.nist.gov
What are the definitions of dawn, dusk and twilight? 

Dawn is the time of morning when the Sun is 6° below the horizon. 
Respectively, dusk occurs when the Sun is 6° below the horizon in the evening. 

Sunrise is the time when the first part of the Sun becomes visible in the morning at a given location.
Sunset is the time when the last part of the Sun disappears below the horizon in the evening at a given location. 
Twilight refers to the period between the dawn and sunrise and between sunset and dusk.
'''

class Suntime:
    def __init__(self, location:tuple):
        self.data = self.get_sunrise_info(location)

    def _get_value(self, valuename):
        if self.data is not None and valuename in self.data:
            return self.data[valuename]
    @property
    def first_light(self):
        return self._get_value('first_light')
    @property
    def dawn(self):
        return self._get_value('dawn')
    @property
    def sunrise(self):
        return self._get_value('sunrise')
    @property
    def solar_noon(self):
        return self._get_value('solar_noon')
    @property
    def golden_hour(self):
        return self._get_value('golden_hour')

    @property
    def sunset(self):
        return self._get_value('sunset')
    @property
    def last_light(self):
        return self._get_value('last_light')
    @property
    def dusk(self):
        return self._get_value('dusk')

    @property
    def y_last_light(self):
        return self._get_value('y_last_light')

    @property
    def t_first_light(self):
        return self._get_value('t_first_light')

    @property
    def day_length(self):
        return self._get_value('day_length')
    @property
    def timezone(self):
        return self._get_value('timezone')

    def map_time(self, t, start, end):
        total = end - start
        partial = t - start
        pct = partial / total
        return pct

    def get_part_of_day(self, now:datetime):
        if now < self.first_light:
            # need yesterday last light
            return 'y_last_light'
        if now > self.first_light and now <= self.dawn:
            return 'first_light'
        if now > self.dawn and now <= self.sunrise:
            return 'dawn'
        if now > self.sunrise and now <= self.solar_noon:
            return 'sunrise'
        if now > self.solar_noon and now <= self.golden_hour:
            return 'solar_noon'
        if now > self.golden_hour and now <= self.sunset:
            return 'golden_hour'
        if now > self.sunset and now <= self.dusk:
            return 'sunset'
        if now > self.dusk and now <= self.last_light:
            return 'dusk'

        return 'last_light'

    def get_part_of_day_percent(self):
        '''
        return the two "suntimes" we are between and the percent
        :return:
        '''
        now = datetime.now()
        pod = self.get_part_of_day(now)

        if pod == 'y_last_light':
            p = self.map_time(now, self.y_last_light, self.first_light)
            return ('y_last_light', 'first_light', p)

        if pod == 'first_light':
            p = self.map_time(now, self.first_light, self.dawn)
            return ('first_light', 'dawn', p)

        if pod == 'dawn':
            p = self.map_time(now, self.dawn, self.sunrise)
            return ('dawn', 'sunrise', p)

        if pod == 'sunrise':
            p = self.map_time(now, self.sunrise, self.solar_noon)
            return ('sunrise', 'solar_noon', p)

        if pod == 'solar_noon':
            p = self.map_time(now, self.solar_noon, self.golden_hour)
            return ('solar_noon', 'golden_hour', p)

        if pod == 'golden_hour':
            p = self.map_time(now, self.golden_hour, self.sunset)
            return ('golden_hour', 'sunset', p)

        if pod == 'sunset':
            p = self.map_time(now, self.sunset, self.dusk)
            return ('sunset', 'dusk', p)

        if pod == 'dusk':
            p = self.map_time(now, self.dusk, self.last_light)
            return ('dusk', 'last_light', p)

        p = self.map_time(now, self.last_light, self.t_first_light)
        return ('last_light', 't_first_light', p)

    def get_sunrise_info(self, location:tuple) -> dict:
        latitude, longitude = location
        url = f'https://api.sunrisesunset.io/json?lat={latitude}&lng={longitude}'
        response = requests.get(url)
        if response.ok:
            data = response.json()
            if 'results' in data:
                d = data['results']
                d['today'] = date.today()
                oneday = timedelta(days=1)
                d['tomorrow'] = date.today() + oneday
                d['yesterday'] = date.today() - oneday
                logging.info(f'{"yesterday":>12}: {d["yesterday"]}')
                logging.info(f'{"today":>12}: {d["today"]}')
                logging.info(f'{"tomorrow":>12}: {d["tomorrow"]}')
                for field in (
                        'first_light',
                        'dawn',
                        'sunrise',
                        'solar_noon',
                        'golden_hour',
                        'sunset',
                        'dusk',
                        'last_light',
                ):
                    d[field] = parse_time(d[field], d['today'])
                    logging.info(f'{field:>12}: {d[field]}')

                d['y_last_light'] = d['last_light'] - oneday
                logging.info(f'{"last yesterday":>12}: {d["y_last_light"]} (approx)')
                d['t_first_light'] = d['first_light'] + oneday
                logging.info(f'{"tomorrow_first":>12}: {d["t_first_light"]} (approx)')

                return d
            else:
                return data
        else:
            logging.info(f'Error getting sun time info: {response}')
            return None