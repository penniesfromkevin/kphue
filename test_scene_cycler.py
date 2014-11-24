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
#      sensor.index_0: {
#          button_id_0: [scene_id_0, .. scene_id_n],
#          ..
#          button_id_n: [scene_id_0, .. scene_id_n],
#          },
#      ..
#      sensor.index_n: {
#          button_id_0: [scene_id_0, .. scene_id_n],
#          ..
#          button_id_n: [scene_id_0, .. scene_id_n],
#          },
#      }
CYCLES = {
        2: {
            17: ('d88f04c36-on-0', '7c4a8792d-on-0',),
            },
        3: {
            34: ('d88f04c36-on-0', '7c4a8792d-on-0',),
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
                rules = my_bridge.get_rules_for_sensor(sensor)
                for rule in rules:
                    for condition in rule.conditions:
                        if ('value' in condition
                                and button == int(condition['value'])):
                            scene_id = settings[sensor.index][button] + 1
                            if scene_id >= len(CYCLES[sensor.index][button]):
                                scene_id = 0
                            scene = CYCLES[sensor.index][button][scene_id]
                            settings[sensor.index][button] = scene_id
                            LOGGER.info('Sensor %s (button %s): %s (index %s)',
                                    sensor.index, button, scene, scene_id)
                            rule.set('scene', scene)
        LOGGER.debug('settings: %s', settings)
    LOGGER.info('~~~ Sample Run complete! ~~~')


if __name__ == '__main__':
    ARGS = parse_args()
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s',
                        level=getattr(logging, ARGS.loglevel))
    POLLING = True
    sys.exit(main())
