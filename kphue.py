# -*- coding: utf-8 -*-
"""My take on a Hue library.

This code borrows heavily from phue by Nathanaël Lécaudé.
https://github.com/studioimaginaire/phue

This software is provided under the MIT license (see LICENSE file).

"Hue Personal Wireless Lighting" is a trademark owned by
Koninklijke Philips Electronics N.V.
"""
__author__ = 'Kevin Park (penniesfromkevin@yahoo)'
__version__ = '0.1.3'
__copyright__ = 'Copyright (c) 2014, Kevin Park (penniesfromkevin@yahoo)'

import collections
import json
import logging
import os
import platform
import socket
import sys
import time

PY3K = sys.version_info[0] > 2
if PY3K:
    import http.client as httplib
else:
    import httplib

COMPLETION_DELAY = 1 # seconds
CONFIG_FILE = '.kphue'
LOGGER = logging.getLogger('kphue')

KELVIN_MIN = 2000
KELVIN_MAX = 6500
MIREDS_MIN = 153
MIREDS_MAX = 500
HUE_MAX = 65535
SAT_MAX = 254
BRI_MAX = 254

if platform.system() == 'Windows':
    USER_HOME = 'USERPROFILE'
else:
    USER_HOME = 'HOME'


class KphueException(Exception):
    """Kphue exception wrapper.
    """
    pass


class KphueTimeout(Exception):
    """Kphue exception wrapper.
    """
    pass


class Bridge(object):
    """Hue Bridge interface.
    """
    def __init__(self, ip=None, user=None, config_file=None):
        """Initialize the Bridge selected.

        Args:
            ip: IP address of the Bridge.
            user: User name to use to connect to Bridge.
            config_file: Path to file containing IP and user information.
        """
        home_dir = os.getenv(USER_HOME)
        if config_file:
            self.config_file = config_file
        elif home_dir and os.access(home_dir, os.W_OK):
            self.config_file = os.path.join(home_dir, CONFIG_FILE)
        elif ('iPod' in platform.machine() or 'iPhone' in platform.machine()
                or 'iPad' in platform.machine()):
            self.config_file = os.path.join(home_dir, 'Documents', CONFIG_FILE)
        else:
            self.config_file = os.path.join(os.getcwd(), CONFIG_FILE)

        self.ip = ip
        self.user = user
        self.name = None

        self._state = None
        self.apiversion = None
        self.swversion = None

        self.localtime = None
        self.timezone = None
        self.zigbeechannel = None
        self.whitelist = None

        self.groups = []
        self.lights = []
        self.rules = []
        self.scenes = []
        self.schedules = []
        self.sensors = []

        self.all_lights = None

        self.connect()
        self.refresh()

    def __repr__(self):
        """Like default repr function, but add object name.

        Returns:
            Object string representation.
        """
        return '<{0}.{1} object "{2}" ({3}) at {4}>'.format(
                self.__class__.__module__, self.__class__.__name__,
                self.name, self.ip, hex(id(self)))

    def connect(self):
        """Connect to the Hue bridge.
        """
        if self.ip and self.user:
            LOGGER.info('Already connected to %s as %s', self.ip, self.user)
            return
        LOGGER.info('Connecting bridge...')
        try:
            with open(self.config_file, 'r') as file_handle:
                config = json.loads(file_handle.read())
            self.ip = config.keys()[0]
            LOGGER.info('Using ip %s', self.ip)
            self.user = config[self.ip]['username']
            LOGGER.info('Using username %s', self.user)
        except IOError:
            LOGGER.warning('Could not read %s; try registering',
                    self.config_file)
        except KeyError:
            LOGGER.warning('Malformed file %s; try registering',
                    self.config_file)
        if not (self.ip and self.user):
            self.register()

    def refresh(self):
        """Refresh certain attribute values from actual Bridge device.
        """
        responses = self.api_request('GET', 'config/')
        self._state = responses
        for attr in self._state:
            if hasattr(self, attr):
                setattr(self, attr, hue_decode(self._state[attr]))

        self.refresh_lights()
        self.refresh_groups()
        self.refresh_rules()
        self.refresh_scenes()
        self.refresh_schedules()
        self.refresh_sensors()

        if self.all_lights:
            self.all_lights.refresh()
        else:
            self.all_lights = Group(self, 0)

    def register(self):
        """Register computer with Hue bridge hardware.
        """
        LOGGER.debug('Registering')
        registration_request = {'devicetype': 'kphue'}
        data = json.dumps(registration_request)
        responses = self.request('POST', '/api', data)
        for response in responses:
            if 'success' in response:
                LOGGER.info('Writing config file %s', self.config_file)
                config_contents = {self.ip: response['success']}
                with open(self.config_file, 'w') as file_handle:
                    file_handle.write(json.dumps(config_contents))
                self.connect()
                break
            elif 'error' in response:
                raise KphueException(response)

    def request(self, mode, address='', data=None, timeout=10):
        """Utility function for HTTP GET/PUT requests for the API.

        Args:
            mode: One of: ('GET', 'DELETE', 'PUT', 'POST')
            address: Connection address.
            data: Optional data required for PUT and POST requests.
            timeout: Timeout for making connections.

        Returns:
            Response object.
        """
        LOGGER.debug('request: %s %s %s', mode, address, data)
        try:
            connection = httplib.HTTPConnection(self.ip, timeout=timeout)
            if mode in ('GET', 'DELETE'):
                connection.request(mode, address)
            elif mode in ('PUT', 'POST'):
                connection.request(mode, address, data)
        except socket.timeout:
            raise KphueTimeout('request: %s %s %s timed out.'
                    % (mode, address, data))
        except socket.error:
            raise KphueException('request: %s %s %s socket.error.'
                    ' Wrong bridge IP?' % (mode, address, data))
        response = connection.getresponse()
        connection.close()
        result_str = response.read()
        if PY3K:
            result_str = str(result_str, encoding='utf-8')
        LOGGER.debug('response: %s', result_str)
        result = json.loads(result_str)
        return result

    def api_request(self, mode, address='', data=None, timeout=10):
        """Request with api and user prepended.

        Args:
            mode: One of: ('GET', 'DELETE', 'PUT', 'POST')
            address: Connection address.
            data: Optional data required for PUT and POST requests.
            timeout: Timeout for making connections.

        Returns:
            Response object.
        """
        api_address = '/api/%s/%s' % (self.user, address)
        response = self.request(mode, api_address, data, timeout)
        return response

    # Groups ###########################################################
    def create_group(self, name, *args):
        """Create a new light Group.

        Args:
            name: Name of new Group.
            args: Light IDs or names to be part of the Group.
                This can also include lists of IDs and names.

        Returns:
            Integer ID of new Group created, or None on error.
        """
        lights = self.get_lights(args)
        address = 'groups'
        data = {
                'name': name,
                'lights': [str(light.index) for light in lights],
                }
        response = self.api_request('POST', address, json.dumps(data))[0]
        if 'success' in response:
            id_string = response['success']['id']
            new_id = int(id_string.split('/')[-1])
        else:
            LOGGER.error('Creating Group %s: %s', name,
                    response['error']['description'])
            new_id = None
        wait()
        self.refresh_groups()
        return new_id

    def delete_group(self, name_or_id):
        """Delete a light Group.

        Args:
            name_or_id: Name (string) or ID (integer) of Group to
                delete.

        Returns:
            Boolean: True on success, False on errors.
        """
        return_status = True
        group = self.get_group(name_or_id)
        if not group:
            LOGGER.warning('No group returned for deletion')
            return_status = False
        else:
            LOGGER.info('%s: Delete', group._identifier)
            address = 'groups/%d' % group.index
            responses = self.api_request('DELETE', address)
            for response in responses:
                if not 'success' in response:
                    LOGGER.error('Group %s: Delete error: %s', name_or_id,
                                 response['error']['description'])
                    return_status = False
        self.refresh_groups()
        return return_status

    def get_group(self, *args):
        """Returns a Group specified by name or ID.

        Args:
            *args: Name (string) or ID (integer) to select.

        Returns:
            Single Group matching the requested name or ID, or None.
        """
        objects = self.get_groups(*args)
        if objects:
            the_one = objects[0]
        else:
            the_one = None
        return the_one

    def get_groups(self, *args):
        """Returns a list of Groups specified by name or ID.

        Args:
            *args: List of names (string) or IDs (integer) to select.

        Returns:
            List of Groups matching the requested names and IDs.
        """
        self.refresh_groups()
        objects = _get_from_pool(self.groups, *args)
        return objects

    def refresh_groups(self):
        """Refreshes the list of Group objects.
        """
        responses = self.api_request('GET', 'groups/')
        for id_string in responses:
            res_id = int(id_string)
            for group in self.groups:
                if group.index == res_id:
                    group.refresh()
                    res_id = None
                    break
            if res_id:
                self.groups.append(Group(self, res_id))

    # Lights ###########################################################
    def get_light(self, *args):
        """Returns a Light specified by name or ID.

        Args:
            *args: Name (string) or ID (integer) to select.

        Returns:
            Single Light matching the requested name or ID, or None.
        """
        objects = self.get_lights(*args)
        if objects:
            the_one = objects[0]
        else:
            the_one = None
        return the_one

    def get_lights(self, *args):
        """Returns a list of Lights specified by name or ID.

        Args:
            *args: List of names (string) or IDs (integer) to select.

        Returns:
            List of Lights matching the requested names and IDs.
        """
        self.refresh_lights()
        objects = _get_from_pool(self.lights, *args)
        return objects

    def refresh_lights(self):
        """Refreshes the list of Light objects.
        """
        responses = self.api_request('GET', 'lights/')
        for id_string in responses:
            res_id = int(id_string)
            for light in self.lights:
                if light.index == res_id:
                    light.refresh()
                    res_id = None
                    break
            if res_id:
                self.lights.append(Light(self, res_id))

    # Rules ############################################################
    def create_rule(self, name, *args):
        """Create a new Rule.

        Args:
            name: Name of new Rule.
            args: data.

        Returns:
            Integer ID of new Rule created, or None on error.
        """
        address = 'rules'
        data = {
                }
        response = self.api_request('POST', address, json.dumps(data))[0]
        if 'success' in response:
            id_string = response['success']['id']
            new_id = int(id_string)
        else:
            LOGGER.error('Creating Rule %s: %s', name,
                    response['error']['description'])
            new_id = None
        self.refresh_rules()
        return new_id

    def delete_rule(self, name_or_id):
        """Delete a Rule.

        Args:
            name_or_id: Name (string) or ID (integer) of Rule to
                delete.

        Returns:
            Boolean: True on success, False on errors.
        """
        rule = self.get_rule(name_or_id)
        LOGGER.info('b.%s: Delete', rule._identifier)
        address = 'rules/%d' % rule.index
        response = self.api_request('DELETE', address)
        return_status = 'success' in response
        if not return_status:
            LOGGER.error('b.%s: Delete error: %s', rule._identifier,
                    response['error']['description'])
        self.refresh_rules()
        return return_status

    def get_rule(self, *args):
        """Returns a Rule specified by name or ID.

        Args:
            *args: Name (string) or ID (integer) to select.

        Returns:
            Single Rule matching the requested name or ID, or None.
        """
        objects = self.get_rules(*args)
        if objects:
            the_one = objects[0]
        else:
            the_one = None
        return the_one

    def get_rules(self, *args):
        """Returns a list of Rules specified by name or ID.

        Args:
            *args: List of names (string) or IDs (integer) to select.

        Returns:
            List of Rules matching the requested names and IDs.
        """
        self.refresh_rules()
        objects = _get_from_pool(self.rules, *args)
        return objects

    def get_rules_for_sensor(self, name_or_id):
        """Get rules for a particular sensor.

        Args:
            name_or_id: Name or ID for sensor.

        Returns:
            List of Rules related to the given sensor.
        """
        sensor = self.get_sensors(name_or_id)
        sensors = []
        for rule in self.rules:
            conditions = [condition for condition in rule.conditions]
            for condition in conditions:
                rule_sensor = int(condition['address'].split('/')[2])
                if rule_sensor == sensor.index:
                    sensors.append(rule)
                    break
        return sensors

    def refresh_rules(self):
        """Refreshes the list of Rule objects.
        """
        responses = self.api_request('GET', 'rules/')
        for id_string in responses:
            res_id = int(id_string)
            for rule in self.rules:
                if rule.index == res_id:
                    rule.refresh()
                    res_id = None
                    break
            if res_id:
                self.rules.append(Rule(self, res_id))

    # Scenes ###########################################################
    def get_scene(self, *args):
        """Returns a Scene specified by name or ID.

        Args:
            *args: Name (string) or ID (integer) to select.

        Returns:
            Single Scene matching the requested name or ID, or None.
        """
        objects = self.get_scenes(*args)
        if objects:
            the_one = objects[0]
        else:
            the_one = None
        return the_one

    def get_scenes(self, *args):
        """Returns a list of Scenes specified by name or ID.

        Args:
            *args: List of names (string) or IDs (integer) to select.

        Returns:
            List of Scenes matching the requested names and IDs.
        """
        self.refresh_scenes()
        objects = _get_from_pool(self.scenes, *args)
        return objects

    def refresh_scenes(self):
        """Refreshes the list of Scene objects.

        Scenes seem to be different from other resources in some way.
        """
        responses = self.api_request('GET', 'scenes/')
        LOGGER.debug('======================================')
        for id_string in responses:
            res_id = int(id_string.split('-')[-1])
            # TODO: format of ID is not as API doc suggests
            LOGGER.debug('scene id_string: %s --> %s', id_string, res_id)
            for scene in self.scenes:
                if scene.index == id_string:
                    scene.refresh()
                    id_string = None
                    break
            if id_string:
                self.scenes.append(Scene(self, id_string))

    # Schedules ########################################################
    def create_schedule(self, name, *args):
        """Create a new Schedule.

        Args:
            name: Name of new Schedule.
            args: data

        Returns:
            Integer ID of new Schedule created, or None on error.
        """
        # TODO
        address = 'schedules'
        data = {
                }
        response = self.api_request('POST', address, json.dumps(data))[0]
        if 'success' in response:
            new_id = int(response['success']['id'])
        else:
            LOGGER.error('Creating Schedule %s: %s', name,
                    response['error']['description'])
            new_id = None
        self.refresh_schedules()
        return new_id

    def get_schedule(self, *args):
        """Returns a Schedule specified by name or ID.

        Args:
            *args: Name (string) or ID (integer) to select.

        Returns:
            Single Schedule matching the requested name or ID, or None.
        """
        objects = self.get_schedules(*args)
        if objects:
            the_one = objects[0]
        else:
            the_one = None
        return the_one

    def get_schedules(self, *args):
        """Returns a list of Schedules specified by name or ID.

        Args:
            *args: List of names (string) or IDs (integer) to select.

        Returns:
            List of Schedules matching the requested names and IDs.
        """
        self.refresh_schedules()
        objects = _get_from_pool(self.schedules, *args)
        return objects

    def delete_schedule(self, name_or_id):
        """Delete a Schedule.

        Args:
            name_or_id: Name (string) or ID (integer) of Schedule to
                delete.

        Returns:
            Boolean: True on success, False on errors.
        """
        schedule = self.get_schedule(name_or_id)
        LOGGER.info('b.%s: Delete', schedule._identifier)
        address = 'schedule/%d' % schedule.index
        response = self.api_request('DELETE', address)
        return_status = 'success' in response
        if not return_status:
            LOGGER.error('b.%s: Delete error: %s', schedule._identifier,
                    response['error']['description'])
        self.refresh_schedules()
        return return_status

    def refresh_schedules(self):
        """Refreshes the list of Schedule objects.
        """
        responses = self.api_request('GET', 'schedules/')
        for id_string in responses:
            res_id = int(id_string)
            for schedule in self.schedules:
                if schedule.index == res_id:
                    schedule.refresh()
                    res_id = None
                    break
            if res_id:
                self.schedules.append(Schedule(self, res_id))

    # Sensors ##########################################################
    def delete_sensor(self, name_or_id):
        """Delete a Sensor.

        Args:
            name_or_id: Name (string) or ID (integer) of Sensor to
                delete.

        Returns:
            Boolean: True on success, False on errors.
        """
        sensor = self.get_sensor(name_or_id)
        LOGGER.info('b.%s: Delete', sensor._identifier)
        address = 'sensor/%d' % sensor.index
        response = self.api_request('DELETE', address)
        return_status = 'success' in response
        if not return_status:
            LOGGER.error('b.%s: Delete error: %s', sensor._identifier,
                    response['error']['description'])
        self.refresh_sensors()
        return return_status

    def get_sensors(self, *args):
        """Returns a Sensor specified by name or ID.

        Args:
            *args: Name (string) or ID (integer) to select.

        Returns:
            Single Sensor matching the requested name or ID, or None.
        """
        objects = self.get_sensors(*args)
        if objects:
            the_one = objects[0]
        else:
            the_one = None
        return the_one

    def get_sensors(self, *args):
        """Returns a list of Sensors specified by name or ID.

        Args:
            *args: List of names (string) or IDs (integer) to select.

        Returns:
            List of Sensors matching the requested names and IDs.
        """
        self.refresh_sensors()
        objects = _get_from_pool(self.sensors, *args)
        return objects

    def refresh_sensors(self):
        """Refreshes the list of Sensor objects.
        """
        responses = self.api_request('GET', 'sensors/')
        for id_string in responses:
            res_id = int(id_string)
            for sensor in self.sensors:
                if sensor.index == res_id:
                    sensor.refresh()
                    res_id = None
                    break
            if res_id:
                self.sensors.append(Sensor(self, res_id))


class HueResource(object):
    """Generic Hue resource object wrapper.
    """
    def __init__(self, parent_bridge, res_id, res_type):
        """
        """
        self.index = res_id
        self.name = None
        self._bridge = parent_bridge
        self._type = res_type
        self._identifier = '%s (%s)' % (self._type, self.index)
        self._state = None

        # Now get the actual values
        self.refresh()

    def __repr__(self):
        """Like default python repr function, but add light name.

        Returns:
            Object string representation.
        """
        return '<{0}.{1} object "{2}" ({3}) at {4}>'.format(
                self.__class__.__module__, self.__class__.__name__,
                self.name, self.index, hex(id(self)))

    def refresh(self):
        """Override this.
        """
        LOGGER.debug('%s: Refreshing', self._identifier)
        self._state = self._bridge.api_request('GET', '%ss/%s' % (self._type,
                self.index))
        # TODO: Scenes error often (errors are list); API doc doesn't have GET
        if isinstance(self._state, list):
            self.name = self.index
        elif PY3K:
            self.name = self._state['name']
        else:
            self.name = self._state['name'].encode('utf-8')
        self._identifier = '%s %s (%s)' % (self._type, self.name, self.index)


class Luminous(HueResource):
    """Wrapper for objects that set light.
    """
    def __init__(self, parent_bridge, res_id, res_type):
        """
        """
        if res_type == 'group':
            self._attr_key = 'action'
        else:
            self._attr_key = 'state'

        self.effect = None
        # "on" Boolean
        self.on = None

        # Color modes: xy, ct, hs
        self.xy = None
        self.ct = None
        self.hue = None
        self.sat = None
        self.bri = None
        self._bri = None
        # added mode: value = tuple(r, g, b), 0 to 255
        self.rgb = None

        # Time in ds (0.1 seconds!)
        self.transitiontime = None

        super(Luminous, self).__init__(parent_bridge, res_id, res_type)

    def refresh(self):
        """Refreshes local attributes with actual values.
        """
        super(Luminous, self).refresh()
        self.on = hue_decode(self._state[self._attr_key]['on'])

        self.effect = hue_decode(self._state[self._attr_key]['effect'])

        self.rgb = None

        self.ct = int(self._state[self._attr_key]['ct'])

        self.hue = int(self._state[self._attr_key]['hue'])
        self.sat = int(self._state[self._attr_key]['sat'])
        self.bri = int(self._state[self._attr_key]['bri'])

        self.xy = validate_xy(self._state[self._attr_key]['xy'])
        self._state[self._attr_key]['xy'] = self.xy

    def turn_on(self):
        """Turns lights on.
        """
        LOGGER.debug('%s: Turning on', self._identifier)
        self.set('on', True)

    def turn_off(self):
        """Turns lights off.
        """
        LOGGER.debug('%s: Turning off', self._identifier)
        self.set('on', False)

    def reset(self):
        """Reset all parameters to show white light.
        """
        LOGGER.debug('Resetting %s resource %s', self._type, self.name)
        self.transitiontime = None
        self.effect = None
        # Only the information for the selected colormode is needed.
        #   http://www.developers.meethue.com/documentation/lights-api
        # colormode is not set directly; follows priority xy > ct > hs.
        # xy is default, but may it be more accurate to send hs-converted rgb?
        self.rgb = None
        rgb = [255, 255, 255]
        self.ct = MIREDS_MIN
        self.xy = rgb_to_xy(rgb)
        self.hue, self.sat, self.bri = rgb_to_hsb(rgb)
        self.bri = BRI_MAX
        # Turns on the light because:
        #   http://www.developers.meethue.com/documentation/lights-api
        # A light cannot have its hue, saturation, brightness, effect, ct or
        # xy modified when it is turned off. Doing so will return error 201.
        self.turn_on()

    def set(self, parameter=None, value=None):
        """Adjust properties of Luminous objects.

        Sets all values, including an optional override.
        Some supported parameters and values:
            'name': string
            'on' : True | False
            'xy' : [0.0 - 1.0, 0.0 - 1.0]
            'ct' : 154 - 500
            'hue': 0 - 65535
            'sat': 0 - 254
            'bri': 0 - 254
            'alert': 'none', 'select', 'lselect'
            'effect': 'none', 'colorloop'
            'transitiontime': 0 - 30000 ds

        Args:
            parameter: Name of API parameter to set.
            value: Value to set.

        Returns:
            Boolean; True on success, False on errors.
        """
        LOGGER.debug('%s: set(%s, %s)?', self._identifier, parameter, value)
        if parameter:
            if hasattr(self, parameter):
                setattr(self, parameter, value)
            else:
                LOGGER.warning('%s: Attribute %s does not exist',
                        self._identifier, parameter)

        return_status = True
        # Set attributes then state
        for path in ('', '/%s' % self._attr_key):
            if path:
                data = self._form_state_data()
            else:
                data = self._form_attribute_data()
            if return_status and data:
                address = '%ss/%s%s' % (self._type, self.index, path)
                json_data = json.dumps(data)
                responses = self._bridge.api_request('PUT', address, json_data)
                for response in responses:
                    if 'error' in response:
                        LOGGER.error('%s: %s', self._identifier,
                                response['error']['description'])
                        return_status = False
                if not path:
                    # self.lights doesn't update fast enough for refresh()
                    wait()

        # Reload set values
        self.refresh()
        return return_status

    def _form_attribute_data(self):
        """Return object of values that have changed.

        Returns:
            Returns data object prepared for API request.
        """
        attrs = {}
        if self.name != self._state['name']:
            attrs['name'] = self.name
        if 'lights' in self._state:
            lights = [int(l_id) for l_id in self._state['lights']]
            for light in self.lights:
                try:
                    lights.remove(light.index)
                except ValueError:
                    lights = True
                    break
            if lights:
                attrs['lights'] = [str(light.index) for light in self.lights]
        if hasattr(self, 'scene') and self.scene:
            attrs['scene'] = self.scene
            self.scene = None
        LOGGER.debug('%s: attributes = %s', self._identifier, attrs)
        return attrs

    def _form_state_data(self):
        """Return object of values that have changed.

        Returns:
            Returns data object prepared for API request.
        """
        # Conform object attributes to valid ranges/values.
        if self.rgb:
            # should 0,0,0 turn the light off?
            if list(self.rgb) == [0, 0, 0]:
                self.on = False
            elif hasattr(self, 'color_mode') and self.color_mode == 'hs':
                self.hue, self.sat, self.bri = rgb_to_hsb(self.rgb)
            else:
                self.xy = rgb_to_xy(self.rgb)
            self.rgb = None
        else:
            self.xy = validate_xy(self.xy)
        LOGGER.debug('hsb = %s %s %s', self.hue, self.sat, self.bri)
        self.ct = constrain_value(self.ct, MIREDS_MIN, MIREDS_MAX)
        self.hue = constrain_value(self.hue, 0, HUE_MAX)
        self.sat = constrain_value(self.sat, 0, SAT_MAX)
        self.bri = constrain_value(self.bri, 0, BRI_MAX)
        if self.transitiontime is not None:
            self.transitiontime = int(round(self.transitiontime))
        if self.effect not in (None, 'colorloop'):
            self.effect = None

        # Some added code here to work around known bug where turning off
        # with transitiontime set makes it restart on brightness = 1
        #   http://www.everyhue.com/vanilla/discussion/204/
        #     bug-with-brightness-when-requesting-ontrue-transitiontime5
        # This now works regardless of how the light is turned on/off.
        on_state = hue_decode(self._state[self._attr_key]['on'])
        if on_state != self.on and self.transitiontime is not None:
            if self.on:
                if self._bri:
                    self.bri = self._bri
                    self._bri = None
            else:
                self._bri = self.bri
                # only changes get applied, so change brightness a little
                if self.bri > 0:
                    self.bri = self._bri - 1
                else:
                    # This will get restored
                    self.bri = 1

        # Only request changes for value that have changed
        states = {}
        for state in self._state[self._attr_key]:
            if hasattr(self, state):
                self_value = getattr(self, state)
                set_value = hue_encode(self_value)
                if self._state[self._attr_key][state] != set_value:
                    states[state] = set_value
                    LOGGER.debug('%s (%s) --> %s', state,
                            self._state[self._attr_key][state], set_value)
        if states and self.transitiontime is not None:
            states['transitiontime'] = self.transitiontime
        # If setting something but light is off, turn light on
        if 'on' not in states and states:
            states['on'] = hue_encode(True)
            LOGGER.debug('Originally off, now on; states: %s', states)
        LOGGER.debug('%s: states = %s', self._identifier, states)
        return states


class Light(Luminous):
    """Light object.
    """
    def __init__(self, parent_bridge, res_id):
        """:w

        """
        self.alert = None
        # These cannot be set, only read:
        self.color_mode = None
        self.is_reachable = None
        self.modelid = None
        self.swversion = None
        super(Light, self).__init__(parent_bridge, res_id, 'light')

    def refresh(self):
        """Refreshes local attributes with actual values.
        """
        super(Light, self).refresh()
        self.alert = hue_decode(self._state['state']['alert'])
        self.color_mode = self._state['state']['colormode']
        self.is_reachable = self._state['state']['reachable']
        # attributes
        self.modelid = hue_decode(self._state['modelid'])
        self.swversion = hue_decode(self._state['swversion'])

    def reset(self):
        """Reset all parameters to show white light.
        """
        self.alert = None
        super(Light, self).reset()

    def set(self, parameter=None, value=None):
        """Sets light attributes and states.

        Args:
            parameter: Name of API parameter to set.
            value: Value to set.

        Returns:
            Boolean; True on success, False on errors.
        """
        if not self.is_reachable:
            return False
        else:
            super(Light, self).set(parameter, value)


class Group(Luminous):
    """Group object.
    """
    def __init__(self, parent_bridge, resource_id):
        """
        """
        self.lights = []
        #self.scenes = None
        self.scene = None
        super(Group, self).__init__(parent_bridge, resource_id, 'group')

    def refresh(self):
        """Refreshes local attributes with actual values.
        """
        super(Group, self).refresh()
        lights = [int(l_id) for l_id in self._state['lights']]
        self.lights = self._bridge.get_lights(lights)
        # scenes are really just stored on light.  Why is this provided?
        #self.scenes = [str(s_id) for s_id in self._state['scenes']]

    def reset(self):
        """Reset all parameters to show white light.
        """
        self.scene = None
        super(Group, self).reset()


class Rule(HueResource):
    """Rule object.
    """
    def __init__(self, parent_bridge, resource_id):
        """
        """
        self.lasttriggered = None
        self.owner = None
        self.status = None
        self.conditions = None
        self.actions = None
        super(Rule, self).__init__(parent_bridge, resource_id, 'rule')

    def refresh(self):
        """Refreshes local attributes with actual values.
        """
        super(Rule, self).refresh()
        for attr in self._state:
            if hasattr(self, attr):
                setattr(self, attr, hue_decode(self._state[attr]))

    def set(self, parameter=None, value=None):
        """Set a Rule attribute.

        Args:
            parameter: Attribute to set.
            value: Value to set.
        """
        # TODO: Just testing action body now, but generalize.
        for action in self.actions:
            if 'body' in action and parameter in action['body']:
                action['body'][parameter] = value
        data = {'actions': self.actions}

        return_status = True
        address = '%ss/%s' % (self._type, self.index)
        json_data = json.dumps(data)
        responses = self._bridge.api_request('PUT', address, json_data)
        for response in responses:
            if 'error' in response:
                LOGGER.error('%s: %s', self._identifier,
                        response['error']['description'])
                return_status = False

        # Reload set values
        self.refresh()
        return return_status

class Scene(HueResource):
    """Scene object.
    """
    def __init__(self, parent_bridge, resource_id):
        """
        """
        self.active = None
        self.lights = None
        super(Scene, self).__init__(parent_bridge, resource_id, 'scene')

    def refresh(self):
        """Refreshes local attributes with actual values.
        """
        super(Scene, self).refresh()


class Schedule(HueResource):
    """Schedule object.
    """
    def __init__(self, parent_bridge, resource_id):
        """
        """
        # Provided by API
        self._command = None
        self.description = None
        self.created = None
        self.localtime = None
        self.time = None
        self.status = None
        self.autodelete = None
        # Added by kphue
        self.group = None
        self.state = None
        # Only provided for timers
        self.starttime = None
        super(Schedule, self).__init__(parent_bridge, resource_id, 'schedule')

    def refresh(self):
        """Refreshes local attributes with actual values.
        """
        super(Schedule, self).refresh()
        self._command = self._state['command']
        if 'address' in self._command:
            self.group = self._command['address'].split('/')[-2]
        if 'body' in self._command:
            self.state = self._command['body']
        self.description = self._state['description']
        self.created = self._state['created']
        self.time = self._state['time']
        self.status = self._state['status']
        self.autodelete = hue_decode(self._state['autodelete'])
        if 'starttime' in self._state:
            self.starttime = self._state['starttime']
        else:
            self.starttime = None
        if 'localtime' in self._state:
            self.localtime = self._state['localtime']
            LOGGER.warning('localtime: %s', self.localtime)
        else:
            self.localtime = None

    def set(self, parameter=None, value=None):
        """Changes the attributes of a Schedule.

        TODO: This may require generalization of Luminous attributes
        and state...
        """
        pass


class Sensor(HueResource):
    """Sensor object.
    """
    def __init__(self, parent_bridge, resource_id):
        """
        "state": {
            "daylight": false,
            "lastupdated": "2014-06-27T07:38:51"
        },
        "config": {
            "on": true,
            "long": "none",
            "lat": "none",
            "sunriseoffset": 50,
            "sunsetoffset": 50
        },
        "name": "Daylight",
        "type": "Daylight",
        "modelid": "PHDL00",
        "manufacturername": "Philips",
        "swversion": "1.0"
        """
        self.state = None
        self.config = None
        self.type = None
        self.modelid = None
        self.manufacturername = None
        self.swversion = None
        super(Sensor, self).__init__(parent_bridge, resource_id, 'sensor')

    def refresh(self):
        """Refreshes local attributes with actual values.
        """
        super(Sensor, self).refresh()
        for attr in self._state:
            if hasattr(self, attr):
                setattr(self, attr, hue_decode(self._state[attr]))


def _get_from_pool(pool, *args):
    """Returns item(s) specified by name or ID from a given pool.

    The results will be a list, even if one or none items match.

    Args:
        pool: List of objects from which to draw items.
        *args: names (string) and/or IDs (integer) of items to get.
            This can be specified as separate items, a list of items,
            or a combination thereof.

    Returns:
        List of objects matching the specifications.
    """
    names = []
    ids = []
    items = list(flatten_struct(args))
    things = []
    for item in items:
        if isinstance(item, int):
            ids.append(item)
        elif isinstance(item, HueResource):
            things.append(item)
        else:
            names.append(str(item))
    things += [thing for thing in pool
               if thing.name in names or thing.index in ids]
    return things


def validate_rgb(r_val, g_val=None, b_val=None):
    """Validates RGB values (0 to 255).

    Args:
        r_val: 0 to 255 value for red, or a list of three integers.
        g_val: 0 to 255 value for green.
        b_val: 0 to 255 value for blue.
        Note that r_val can also be a list containing all three values,
        which precludes the need to set g_val and b_val separately.

    Returns:
        Returns a list containing two items, x and y: [x, y]
    """
    # Handle the case where a list trio is submitted
    if isinstance(r_val, collections.Iterable):
        r_val, g_val, b_val = r_val
    r_val = constrain_value(int(r_val), 0, 255)
    g_val = constrain_value(int(g_val), 0, 255)
    b_val = constrain_value(int(b_val), 0, 255)
    return [r_val, g_val, b_val]


def validate_xy(x_val, y_val=None):
    """Validates XY values (0.0 to 1.0).

    Args:
        x_val: 0.0 to 1.0 value for X.
        y_val: 0.0 to 1.0 value for Y.
        Note that x_val can also be a list containing both values,
        which precludes the need to set y_val separately.

    Returns:
        Returns a list containing two items, x and y: [x, y]
    """
    # Handle the case where a list pair is submitted
    if isinstance(x_val, collections.Iterable):
        x_val, y_val = x_val
    x_val = constrain_value(float(x_val), 0.0, 1.0)
    y_val = constrain_value(float(y_val), 0.0, 1.0)
    return [x_val, y_val]


def rgb_to_xy(r_val, g_val=None, b_val=None):
    """Converts RGB (0 to 255) values to xy values.

    TODO: This should also take into account the TYPE of Hue light, as
    they may have different color spaces.  If that happens, this may
    find itself as part of the Light methods again.

    From:
    https://github.com/PhilipsHue/PhilipsHueSDK-iOS-OSX/blob/master/
        ApplicationDesignNotes/RGB%20to%20xy%20Color%20conversion.md
    For the hue bulb the corners of the triangle are:
      Red:   0.674, 0.322
      Green: 0.408, 0.517
      Blue:  0.168, 0.041

    For LivingColors Bloom, Aura and Iris the triangle corners are:
      Red:   0.703, 0.296
      Green: 0.214, 0.709
      Blue:  0.139, 0.081

    If you have light which is not one of those, you should use:
      Red:   1.0, 0
      Green: 0.0, 1.0
      Blue:  0.0, 0.0

    Usage:
        # my_light is a Light object:
        my_light.xy = rgb_to_xy(153, 0, 255)
        # or
        # my_light.xy = rgb_to_xy([153, 0, 255])
        my_light.set()

    Args:
        r_val: 0 to 255 value for red, or a list of three integers.
        g_val: 0 to 255 value for green.
        b_val: 0 to 255 value for blue.
        Note that r_val can also be a list containing all three values,
        which precludes the need to set g_val and b_val separately.

    Returns:
        Returns a list containing two items, x and y: [x, y]
    """
    def make_vivid(value):
        """Normalize to (0.0, 1.0) and boost color.

        Args:
            value: red, green, or blue integer value between 0 and 255.

        Returns:
            Normalized float between 0.0 and 1.0.
        """
        v_norm = value / 255.0
        if v_norm > 0.04045:
            vivid = pow((v_norm + 0.055) / 1.055, 2.4)
        else:
            vivid = v_norm / 12.92
        return vivid

    r_val, g_val, b_val = validate_rgb(r_val, g_val, b_val)
    r_fin = make_vivid(r_val)
    g_fin = make_vivid(g_val)
    b_fin = make_vivid(b_val)
    x_val = r_fin * 0.649926 + g_fin * 0.103455 + b_fin * 0.197109
    y_val = r_fin * 0.234327 + g_fin * 0.743075 + b_fin * 0.022598
    z_val = r_fin * 0.000000 + g_fin * 0.053077 + b_fin * 1.035763

    # Convert to xy color point
    if x_val + y_val + z_val:
        xy_x = x_val / (x_val + y_val + z_val)
        xy_y = y_val / (x_val + y_val + z_val)
    else:
        xy_x = xy_y = 0
    x_y = validate_xy(xy_x, xy_y)
    LOGGER.debug('RGB (%d, %d, %d) is xy %s', r_val, g_val, b_val, x_y)
    return x_y


def rgb_to_hsb(r_val, g_val=None, b_val=None):
    """Converts RGB (0 to 255) values to HSB values.

    Usage:
        # my_light is a Light object:
        my_light.hue, my_light.sat, my_light.bri = rgb_to_hsb(
                [255, 255, 255])
        my_light.set()

    Args:
        r_val: 0 to 255 value for red, or a list of three integers.
        g_val: 0 to 255 value for green.
        b_val: 0 to 255 value for blue.
        Note that r_val can also be a list containing all three values,
        which precludes the need to set g_val and b_val separately.

    Returns:
        Returns a list containing three items: hue, saturation, and
        brightness.
    """
    r_val, g_val, b_val = validate_rgb(r_val, g_val, b_val)
    r_norm = r_val / 255.0
    g_norm = g_val / 255.0
    b_norm = b_val / 255.0
    rgb_min = min(r_norm, min(g_norm, b_norm))
    rgb_max = max(r_norm, max(g_norm, b_norm))

    if rgb_min == rgb_max:
        # Black-gray-white
        hue_norm = 0
        sat_norm = 0
        bri_norm = rgb_min
    else:
        # Colors other than black-gray-white:
        if r_norm == rgb_min:
            delta = g_norm - b_norm
            huey = 3
        elif b_norm == rgb_min:
            delta = r_norm - g_norm
            huey = 1
        else:
            delta = b_norm - r_norm
            huey = 5
        hue_norm = 60 * (huey - delta / (rgb_max - rgb_min))
        sat_norm = (rgb_max - rgb_min) / rgb_max
        bri_norm = rgb_max
    hue = int(HUE_MAX * hue_norm / 360.0)
    saturation = int(sat_norm * SAT_MAX)
    brightness = int(bri_norm * BRI_MAX)
    LOGGER.debug('RGB (%d, %d, %d) is HSB %d, %d, %d', r_val, g_val, b_val,
            hue, saturation, brightness)
    return [hue, saturation, brightness]


def kelvin_to_mireds(kelvin):
    """Converts color temperature in Kelvin to mireds.

    TODO: This should also take into account the TYPE of Hue light?

    Usage:
        # my_light is a Light object:
        my_light.ct = kelvin_to_mireds(5700)
        my_light.set()

    Args:
        kelvin: Color temperature in Kelvin.

    Returns:
        Integer color temperature in mireds.
    """
    kelvin = constrain_value(kelvin, KELVIN_MIN, KELVIN_MAX)
    mireds = int(round(1e6 / kelvin))
    LOGGER.debug('kelvin_to_mireds(): %d K is %d mireds', kelvin, mireds)
    return mireds


def flatten_struct(struct):
    """Flattens a complex structure to a simple list.

    [[[1, 2, 3], [4, 5]], 6]
    becomes
    [1, 2, 3, 4, 5, 6]

    Args:
        fluff: The structure to flatten.

    Returns:
        A simple list.
    """
    for item in struct:
        if (isinstance(item, collections.Iterable)
                and not isinstance(item, basestring)):
            for subitem in flatten_struct(item):
                yield subitem
        else:
            yield item


def constrain_value(value, bound_min, bound_max):
    """Contrains a given numeric value to minimum and maximum values.

    Args:
        value: Value to contrain.
        bound_min: Minimum allowed value.
        bound_max: Maximum allowed value.

    Returns:
        Returns the value bounded by minimum and maximum bounds.
    """
    if bound_min > bound_max:
        bound_min, bound_max = bound_max, bound_min
    if value < bound_min:
        LOGGER.debug('Value (%s) cannot be below %s', value, bound_min)
        value = bound_min
    elif value > bound_max:
        LOGGER.debug('Value (%s) cannot exceed %s', value, bound_max)
        value = bound_max
    return value


def hue_encode(value):
    """Returns Hue API-ized version of a Python value.

    Args:
        value: Python value to be converted.

    Returns:
        Hue API representation.
    """
    if value is None:
        return_value = 'none'
    else:
        return_value = value
    return return_value


def hue_decode(value):
    """Returns Pythonized version of a Hue API value.

    Args.
        value: Hue API value to be converted.

    Returns:
        Python representation.
    """
    if value == 'none':
        return_value = None
    elif (isinstance(value, bool) or isinstance(value, int)
            or isinstance(value, float)):
        return_value = value
    elif '.' in value:
        try:
            return_value = float(value)
        except (ValueError, TypeError):
            return_value = value
    else:
        try:
            return_value = int(value)
        except (ValueError, TypeError):
            return_value = value
    return return_value


def debug(loglevel='DEBUG'):
    """Start library logging manually (for interactive shell testing).
    """
    loglevel = getattr(logging, loglevel)
    logging.basicConfig(level=loglevel)


def wait(delay=COMPLETION_DELAY):
    """Sleeps for a given amount of time.

    Args:
        delay: Optional amount of time to delay; ~1 second it not set.
    """
    time.sleep(delay)


if __name__ == '__main__':
    import argparse

    debug_log()

    parser = argparse.ArgumentParser()
    parser.add_argument('-b', '--bridge', help='Bridge IP address.')
    parser.add_argument('-c', '--config_file',
            help='Path to %s.' % CONFIG_FILE)
    ARGS = parser.parse_args()

    bridge = None
    for _ in range(3):
        try:
            bridge = Bridge(ARGS.bridge, config_file=ARGS.config_file)
            break
        except KphueException:
            try:
                input('Press button on Bridge then hit Enter to try again')
            except SyntaxError:
                pass
            LOGGER.info('Retrying connection to bridge.')
    LOGGER.info('Bridge: %s', bridge)
