#!/usr/bin/python
"""Cycle Sensor Test of Kphue.

Allows a single sensor button to cycle amongst several different scenes.
This requires preparation (CYCLES dictionary must be set up manually,
or via a config file (coming)).
"""
import datetime
import logging
import signal
import sys
import time

from argparse import ArgumentParser
from dateutil import parser as dateparser, tz as datetz

import kphue

DEFAULT_DELAY = 2
#Button 1    34
#Button 2    16
#Button 3    17
#Button 4    18
BUTTONS = (34, 16, 17, 18)

# TODO: read this in from a config file
# CYCLES Format:
# {
#      sensor_index_0: {
#          button_id_0: {
#              'lights': [light_0, .., light_n],
#              'rgb': [rgb_triad_0, .. rgb_triad_n],
#              },
#          ..
#          button_id_n: {
#              'lights': [light_0, .., light_n],
#              'rgb': [rgb_triad_0, .. rgb_triad_n],
#              },
#          },
#      ..
#      sensor_index_1: {
#          button_id_0: {
#              'lights': [light_0, .., light_n],
#              'rgb': [rgb_triad_0, .. rgb_triad_n],
#              },
#          ..
#          button_id_n: {
#              'lights': [light_0, .., light_n],
#              'rgb': [rgb_triad_0, .. rgb_triad_n],
#              },
#          },
#      }
CYCLES = {
        2: {
            17: {
                'rgb': ((255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)),
                'lights': ('BackOrbA', 'BackStand'),
                },
            },
        }

LOG_LEVELS = ('CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG')
DEFAULT_LOG_LEVEL = LOG_LEVELS[3]
LOGGER = logging.getLogger()


def parse_args():
    """Parse user arguments and return as parser object.

    Returns:
        Parser object with arguments as attributes.
    """
    parser = ArgumentParser(description='Test basic Kphue functionality.')
    parser.add_argument('-b', '--bridge',
            help='IP of Bridge.')
    parser.add_argument('-d', '--delay', default=DEFAULT_DELAY, type=int,
            help='Delay between sensor checks, in seconds.')
    parser.add_argument('-n', '--light_name',
            help='Name of light to use.')
    parser.add_argument('-L', '--loglevel', choices=LOG_LEVELS,
            default=DEFAULT_LOG_LEVEL, help='Set the logging level.')
    args = parser.parse_args()
    return args


def stop_polling(signum, frame):
    """Stops the infinite loop.

    Args:
        signum: Signal number.
        frame: Frame.
    """
    global POLLING
    print('\n')
    LOGGER.info('Caught SIGTERM; Attempting to exit gracefully')
    POLLING = False


def main():
    """Main script.
    """
    # Catch signals
#    signal.signal(signal.SIGTERM, stop_polling)
    signal.signal(signal.SIGINT, stop_polling)

    my_bridge = kphue.Bridge(ARGS.bridge)

    # Set up initial settings for the sensors
    settings = {}
    for sensor in my_bridge.sensors:
        settings[sensor.index] = {}
        for button in BUTTONS:
            # Initial index in CYCLES
            settings[sensor.index][button] = 0

    LOGGER.info('Polling starting...')
    while POLLING:
        time.sleep(ARGS.delay)
        for sensor in my_bridge.sensors:
            sensor.refresh()
            time_orig = sensor.state['lastupdated']
            if time_orig not in ('none', None):
                time_py = dateparser.parse('%s+00:00' % time_orig)
            else:
                continue
            time_now = datetime.datetime.now(datetz.tzlocal())
            time_diff = time_now - time_py
            if time_diff.seconds < int(ARGS.delay * 1.5):
                button = int(sensor.state['buttonevent'])
                if button not in CYCLES[sensor.index]:
                    continue
                setting_id = settings[sensor.index][button] + 1
                if setting_id >= len(CYCLES[sensor.index][button]['rgb']):
                    setting_id = 0
                color = CYCLES[sensor.index][button]['rgb'][setting_id]
                settings[sensor.index][button] = setting_id
                LOGGER.info('Changed Sensor %s (button %s): %s',
                        sensor.index, setting_id, color)
                if ARGS.light_name:
                    light_query = ARGS.light_name
                elif 'lights' in CYCLES[sensor.index][button]:
                    light_query = CYCLES[sensor.index][button]['lights']
                my_lights = my_bridge.get_lights(light_query)
                for light in my_lights:
                    light.set('rgb', color)
        LOGGER.debug('settings: %s', settings)
    LOGGER.info('~~~ Sample Run complete! ~~~')


if __name__ == '__main__':
    ARGS = parse_args()
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s',
                        level=getattr(logging, ARGS.loglevel))
    POLLING = True
    sys.exit(main())
