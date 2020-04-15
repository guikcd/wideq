#!/usr/bin/env python3

import wideq
import ssl
import time
import argparse
import sys
import re
import os.path
import logging
import traceback
from typing import List
from flask import Flask, json, jsonify

api = Flask(__name__)

LOGGER = logging.getLogger("wideq.server")
STATE_FILE = 'wideq_state.json'

# state is client global config
state = {}


@api.route('/ping', methods=['GET'])
def get_ping():
    """check if server is alive"""
    return jsonify({"running": "ok"}), 200

@api.route('/log/<string:level>', methods=['GET', 'POST'])
def set_log(level):
    """change log level for application: [debug|info|warn|error]"""
    level = level.lower()
    if level == 'debug':
        lvl = logging.DEBUG
    elif level == 'info':
        lvl = logging.INFO
    elif level == 'warn':
        lvl = logging.WARNING
    elif level == 'error':
        lvl = logging.ERROR
    else:
        return jsonify({"unknown log": level, "result": "ko"}), 404

    wideq.set_log_level(lvl)
    LOGGER.setLevel(lvl)        
    return jsonify({'log':level,'result':'ok'}), 200

@api.route('/save', methods=['GET'])
def get_save_default():
    return get_save(STATE_FILE)

@api.route('/save/<string:file>', methods=['GET'])
def get_save(file):
    """Save the updated state to a local json file"""
    with open(file, 'w') as f:
        json.dump(state, f)
        LOGGER.debug("Wrote state file '%s'", os.path.abspath(file))
    return jsonify({'result':'ok'}), 200

@api.route('/gateway/<string:country>/<string:language>', methods=['GET'])
def get_auth(country, language):
    """get the auth Url for country and market"""
    global state

    LOGGER.debug('get auth with country %s and lang %s ', country, language)

    if not country:
        country = wideq.DEFAULT_COUNTRY

    country_regex = re.compile(r"^[A-Z]{2,3}$")
    if not country_regex.match(country):
        msg = "Country must be two or three letters" \
           " all upper case (e.g. US, NO, KR) got: '{}'".format( country)
        LOGGER.error(msg)
        return jsonify({"err":msg}), 401

    if not language:
        language = wideq.DEFAULT_LANGUAGE

    language_regex = re.compile(r"^[a-z]{2,3}-[A-Z]{2,3}$")
    if not language_regex.match(language):
        msg = "Language must be a combination of language" \
           " and country (e.g. en-US, no-NO, kr-KR)" \
           " got: '{}'".format(language)
        LOGGER.error(msg)
        return jsonify({"err":msg}), 401

    LOGGER.info("auth country=%s, lang=%s", country, language )

    client = wideq.Client.load(state)
    if country:
        client._country = country
    if language:
        client._language = language

    gateway = client.gateway
    login_url = gateway.oauth_url()
    # Save the updated state.
    state = client.dump()
        
    return jsonify({'url':login_url}), 200

@api.route('/auth', methods=['GET'])
def get_auth_default():
    LOGGER.debug('get default auth')
    return get_auth(wideq.DEFAULT_COUNTRY, wideq.DEFAULT_LANGUAGE)

@api.route('/token/<path:token>', methods=['GET', 'POST'])
def get_token(token):
    """URL from LG login with the token"""
    global state

    client = wideq.Client.load(state)
    client._auth = wideq.Auth.from_url(client.gateway, token)
    # Save the updated state.
    state = client.dump()
    return jsonify({'token':'ok'}), 200


#
#
#   list of available commands
#
#

@api.route('/ls', methods=['GET' ])
def get_ls():
    """List the user's devices."""
    global state
    
    client = wideq.Client.load(state)
    LOGGER.debug('ls with client=' + json.dumps(client.dump()))
    client.refresh()
    LOGGER.debug('ls with client=' + json.dumps(client.dump()))
    
    # Loop to retry if session has expired.
    while True:
        try:
            result = []
            for device in client.devices:
                LOGGER.debug('{0.id}: {0.name} ({0.type.name} {0.model_id})'.format(device))
                result.append({'id':device.id, 'name':device.name, 'type':device.type.name, 'model':device.model_id})
            LOGGER.debug(str(len(result)) + ' elements: ' + str(result))

            # Save the updated state.
            state = client.dump()
            
            return jsonify(result), 200

        except wideq.NotLoggedInError:
            LOGGER.info('Session expired.')
            client.refresh()

        except UserError as exc:
            LOGGER.error(exc.msg)
            return jsonify({'msg':exc.msg}), 401
            
@api.route('/mon/<device>', methods=['GET' ])
def mon( device_id):
    """Monitor any device, displaying generic information about its
    status.
    """

    client = wideq.Client.load(state)
    device = client.get_device(device_id)
    model = client.model_info(device)

    with wideq.Monitor(client.session, device_id) as mon:
        try:
            while True:
                time.sleep(1)
                print('Polling...')
                data = mon.poll()
                if data:
                    try:
                        res = model.decode_monitor(data)
                    except ValueError:
                        print('status data: {!r}'.format(data))
                    else:
                        for key, value in res.items():
                            try:
                                desc = model.value(key)
                            except KeyError:
                                print('- {}: {}'.format(key, value))
                            if isinstance(desc, wideq.EnumValue):
                                print('- {}: {}'.format(
                                    key, desc.options.get(value, value)
                                ))
                            elif isinstance(desc, wideq.RangeValue):
                                print('- {0}: {1} ({2.min}-{2.max})'.format(
                                    key, value, desc,
                                ))

        except KeyboardInterrupt:
            pass


def ac_mon(client, device_id):
    """Monitor an AC/HVAC device, showing higher-level information about
    its status such as its temperature and operation mode.
    """

    device = client.get_device(device_id)
    if device.type != wideq.DeviceType.AC:
        print('This is not an AC device.')
        return

    ac = wideq.ACDevice(client, device)

    try:
        ac.monitor_start()
    except wideq.core.NotConnectedError:
        print('Device not available.')
        return

    try:
        while True:
            time.sleep(1)
            state = ac.poll()
            if state:
                print(
                    '{1}; '
                    '{0.mode.name}; '
                    'cur {0.temp_cur_f}°F; '
                    'cfg {0.temp_cfg_f}°F; '
                    'fan speed {0.fan_speed.name}'
                    .format(
                        state,
                        'on' if state.is_on else 'off'
                    )
                )

    except KeyboardInterrupt:
        pass
    finally:
        ac.monitor_stop()


class UserError(Exception):
    """A user-visible command-line error.
    """
    def __init__(self, msg):
        self.msg = msg


def _force_device(client, device_id):
    """Look up a device in the client (using `get_device`), but raise
    UserError if the device is not found.
    """
    device = client.get_device(device_id)
    if not device:
        raise UserError('device "{}" not found'.format(device_id))
    return device


def set_temp(client, device_id, temp):
    """Set the configured temperature for an AC device."""

    ac = wideq.ACDevice(client, _force_device(client, device_id))
    ac.set_fahrenheit(int(temp))


def turn(client, device_id, on_off):
    """Turn on/off an AC device."""

    ac = wideq.ACDevice(client, _force_device(client, device_id))
    ac.set_on(on_off == 'on')


def ac_config(client, device_id):
    ac = wideq.ACDevice(client, _force_device(client, device_id))
    print(ac.get_filter_state())
    print(ac.get_mfilter_state())
    print(ac.get_energy_target())
    print(ac.get_power(), " watts")
    print(ac.get_outdoor_power(), " watts")
    print(ac.get_volume())
    print(ac.get_light())
    print(ac.get_zones())

def _build_ssl_context(maximum_version=None, minimum_version=None):
    if not hasattr(ssl, "SSLContext"):
        raise RuntimeError("httplib2 requires Python 3.2+ for ssl.SSLContext")

    context = ssl.SSLContext(ssl.PROTOCOL_TLS)
    context.verify_mode = ssl.CERT_NONE

    # SSLContext.maximum_version and SSLContext.minimum_version are python 3.7+.
    # source: https://docs.python.org/3/library/ssl.html#ssl.SSLContext.maximum_version
    if maximum_version is not None:
        if hasattr(context, "maximum_version"):
            context.maximum_version = getattr(ssl.TLSVersion, maximum_version)
        else:
            raise RuntimeError("setting tls_maximum_version requires Python 3.7 and OpenSSL 1.1 or newer")
    if minimum_version is not None:
        if hasattr(context, "minimum_version"):
            context.minimum_version = getattr(ssl.TLSVersion, minimum_version)
        else:
            raise RuntimeError("setting tls_minimum_version requires Python 3.7 and OpenSSL 1.1 or newer")

    # check_hostname requires python 3.4+
    # we will perform the equivalent in HTTPSConnectionWithTimeout.connect() by calling ssl.match_hostname
    # if check_hostname is not supported.
    if hasattr(context, "check_hostname"):
        context.check_hostname = False

    return context 

if __name__ == '__main__':
    logging.basicConfig(filename='server.log',level=logging.INFO)
    context = _build_ssl_context( 'TLSv1', 'TLSv1')
    api.run(port=5025)