#!/usr/bin/python
"""Test of Kphue.
"""
import logging
import sys

from argparse import ArgumentParser

import kphue

INTS = ('hue', 'sat', 'bri', 'ct',)
COMPS = ('xy', 'rgb',)
BOOLS = ('on',)
OTHERS = ('reset', 'effect', 'alert',)
PARAMETERS = INTS + COMPS + BOOLS + OTHERS

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
    parser.add_argument('-n', '--light_name',
            help='Name of a light that exists on the bridge.')
    parser.add_argument('-i', '--light_id', type=int,
            help='ID of a light that exists on the bridge.')
    parser.add_argument('-p', '--parameter', required=True,
            choices=PARAMETERS, help='Light parameter to set.')
    parser.add_argument('-v', '--value',
            help='Value of parameter to set.')
    parser.add_argument('-L', '--loglevel', choices=LOG_LEVELS,
            default=DEFAULT_LOG_LEVEL, help='Set the logging level.')
    args = parser.parse_args()
    return args


def main():
    """Main script.
    """
    my_bridge = kphue.Bridge(ARGS.bridge)

    if not (ARGS.light_name or ARGS.light_id):
        LOGGER.warning('No Light specified; showing list of lights.')
        for light in my_bridge.lights:
            LOGGER.info('Light ID %d is named %s', light.index, light.name)
        return 0

    my_light = my_bridge.get_light(ARGS.light_name, ARGS.light_id)
    LOGGER.debug('Light found: %s', my_light)

    if my_light:
        LOGGER.info('Found Light %s', my_light.name)
    else:
        LOGGER.error('Could not find specified light.')
        return 1

    if ARGS.parameter == 'reset':
        my_light.reset()
        return 0
    elif ARGS.parameter in INTS:
        ARGS.value = int(ARGS.value)
    elif ARGS.parameter in BOOLS:
        ARGS.value = ARGS.value[0].lower() == 't'
    elif ARGS.parameter in COMPS:
        vals = ARGS.value.split(',')
        if ARGS.parameter == 'xy':
            ARGS.value = kphue.validate_xy(vals)
        else:
            ARGS.value = kphue.validate_rgb(vals)

    my_light.set(ARGS.parameter, ARGS.value)
    LOGGER.info('~~~ Sample Run complete! ~~~')


if __name__ == '__main__':
    ARGS = parse_args()
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s',
                        level=getattr(logging, ARGS.loglevel))
    sys.exit(main())
