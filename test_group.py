#!/usr/bin/python
"""Test of Kphue.
"""
import logging
import sys
import time

from argparse import ArgumentParser

import kphue

GROUP_NAME = 'TestGroup'
BAD_NAME = 'BadName'
BAD_ID = 31415
COLORS = (
        (255, 0, 0),
        (0, 255, 0),
        (0, 0, 255),
        (255, 255, 0),
        )
ALERT_DELAY = 20
DELAY1 = 3
DELAY2 = 5

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
    parser.add_argument('-d', '--delete', action='store_true',
            help='Delete group after test.')
    parser.add_argument('-n', '--group_name', default=GROUP_NAME,
            help='Name of a group that exists on the bridge.')
    parser.add_argument('-N', '--bad_name', default=BAD_NAME,
            help='Name of a group that DOES NOT exist on the bridge.')
    parser.add_argument('-l', '--lights',
            help='Light IDs to add to groupi, comma-separated.')
    parser.add_argument('-L', '--loglevel', choices=LOG_LEVELS,
            default=DEFAULT_LOG_LEVEL, help='Set the logging level.')
    args = parser.parse_args()
    return args


def main():
    """Main script.
    """
    my_bridge = kphue.Bridge(ARGS.bridge)
    LOGGER.info('Bridge %s', my_bridge)

    LOGGER.info('Groups: %s', my_bridge.groups)

    my_group = my_bridge.get_group(ARGS.group_name)
    if not my_group:
        LOGGER.info('Could not get group %s, so creating it', ARGS.group_name)
        if ARGS.lights:
            light_ids = ARGS.lights.split(',')
            lights = []
            for light_id in light_ids:
                try:
                    light = int(light_id)
                except ValueError:
                    light = light_id
                lights.append(light)
            LOGGER.info('Using lights %s', lights)
        else:
            lights = [light for light in my_bridge.lights[:3]]
            LOGGER.info('Adding lights %s', lights)
        group_id = my_bridge.create_group(ARGS.group_name, lights)
        my_group = my_bridge.get_group(group_id)
    LOGGER.info('Got group %s', my_group.name)

    for rgb in COLORS:
        LOGGER.info('Setting RGB %s', rgb)
        my_group.set('rgb', rgb)
        kphue.wait(DELAY1)

    for light in my_group.lights:
        LOGGER.info('Setting alert')
        light.set('alert', 'lselect')

    LOGGER.info('Sleeping %d for alert', ALERT_DELAY)
    kphue.wait(ALERT_DELAY)

    LOGGER.info('Resetting')
    my_group.reset()

    LOGGER.info('Turning off')
    my_group.set('on', False)

    if ARGS.delete:
        LOGGER.info('Deleting')
        my_bridge.delete_group(my_group)

    LOGGER.info('~~~ Sample Run complete! ~~~')


if __name__ == '__main__':
    ARGS = parse_args()
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s',
                        level=getattr(logging, ARGS.loglevel))
    sys.exit(main())
