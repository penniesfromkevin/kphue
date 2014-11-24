#!/usr/bin/python
"""Test of Kphue.
"""
import logging
import sys
import time

from argparse import ArgumentParser

import kphue

BAD_NAME = 'BadName'
BAD_ID = 31415
COLORS = (
        (0, 0, 255),
        (0, 255, 0),
        (255, 0, 0),
        (153, 0, 255),
        )
DELAY1 = 5
DELAY2 = 3

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
    parser.add_argument('-N', '--bad_name', default=BAD_NAME,
            help='Name of a light that DOES NOT exist on the bridge.')
    parser.add_argument('-L', '--loglevel', choices=LOG_LEVELS,
            default=DEFAULT_LOG_LEVEL, help='Set the logging level.')
    args = parser.parse_args()
    return args


def main():
    """Main script.
    """
    my_bridge = kphue.Bridge(ARGS.bridge)
    LOGGER.info('Bridge %s', my_bridge)

    # Get bridge state (This returns the full dictionary that you can explore)
    response = my_bridge.api_request('GET')
    LOGGER.info('Full API dictionary: %s', response)

    for light in my_bridge.lights:
        LOGGER.info('%d (%s) is on? %s reachable? %s', light.index, light.name,
                light.on, light.is_reachable)

    # Get light by name
    my_light = my_bridge.get_light(ARGS.bad_name)
    LOGGER.info('Bad light name: %s returns %s', ARGS.bad_name, my_light)

    if my_light:
        LOGGER.warning('Should not see this: %s', my_light._state)

    if not ARGS.light_name:
        if my_bridge.lights:
            good_name = my_bridge.lights[0].name
        else:
            LOGGER.error('No lights found on bridge %s', ARGS.bridge)
            return 1
    else:
        good_name = ARGS.light_name

    my_light = my_bridge.get_light(good_name)
    LOGGER.info('Good light name: %s returns %s', good_name, my_light)

    if not my_light:
        LOGGER.error('Light %s not found', good_name)
        return 2

    # Set default light value
    LOGGER.info('Resetting light %s', my_light.name)
    my_light.reset()

    # Turns light off and on
    my_light.transitiontime = 50
    for _ in range(2):
        LOGGER.info('Light off; transitiontime: %d', my_light.transitiontime)
        my_light.turn_off()
        time.sleep(DELAY1)
        my_light.turn_on()
        LOGGER.info('Light on; transitiontime: %d', my_light.transitiontime)
        time.sleep(DELAY1)
    my_light.transitiontime = None

    LOGGER.info('HSB color')
    for color in COLORS:
        my_light.hue, my_light.sat, my_light.bri = kphue.rgb_to_hsb(color)
        LOGGER.info('RGB: %s || H: %d, S: %d, B: %d', color,
                my_light.hue, my_light.sat, my_light.bri)
        my_light.set()
        time.sleep(DELAY2)

    # Set default light value
    LOGGER.info('Resetting light %s', my_light.name)
    my_light.reset()

    LOGGER.info('RGB color')
    for color in COLORS:
        my_light.rgb = color
        for brightness in range(0, 256, 85):
            my_light.bri = brightness
            LOGGER.info('RGB: %s | Brightness: %d', color, my_light.bri)
            my_light.set()
            time.sleep(DELAY2)

    # Set default light value
    LOGGER.info('Resetting light %s', my_light.name)
    my_light.reset()

    LOGGER.info('XY color')
    for color in COLORS:
        my_light.xy = kphue.rgb_to_xy(color)
        for brightness in range(0, 256, 85):
            my_light.bri = brightness
            LOGGER.info('RGB: %s || XY: %s || Brightness: %d', color,
                    my_light.xy, my_light.bri)
            my_light.set()
            time.sleep(DELAY2)

    # Set default light value
    LOGGER.info('Resetting light %s', my_light.name)
    my_light.reset()

    LOGGER.info('Turning off light %s', my_light.name)
    my_light.turn_off()
    LOGGER.info('~~~ Sample Run complete! ~~~')


if __name__ == '__main__':
    ARGS = parse_args()
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(message)s',
                        level=getattr(logging, ARGS.loglevel))
    sys.exit(main())
