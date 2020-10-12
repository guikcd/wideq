#!/usr/bin/env python3

import wideq
import json
import time
import argparse
import sys
import re
import os.path
import logging
from typing import List

from pyJeedom import jeedom

logging.basicConfig(filename='lgthinq.log', format='%(asctime)s:%(levelname)s:%(message)s', level=logging.INFO)
LOGGER = logging.getLogger(__name__)
STATE_FILE = 'wideq_state.json'


def ls(jee, client):
    """List the user's devices."""

    for device in client.devices:
        LOGGER.info('{0.id}: {0.name} ({0.type.name} {0.model_id})'.format(device))


def mon(jee, client, device_id):
    """Monitor any device, displaying generic information about its
    status.
    """

    device = client.get_device(device_id)
    model = client.model_info(device)

    with wideq.Monitor(client.session, device_id) as mon:
        try:
            while True:
                time.sleep(1)
                LOGGER.info('Polling...')
                data = mon.poll()
                if data:
                    try:
                        res = model.decode_monitor(data)
                    except ValueError:
                        LOGGER.warning('device {}: status data: {!r}'.format(device_id, data))
                    else:
                        for key, value in res.items():
                            try:
                                desc = model.value(key)
                            except KeyError:
                                LOGGER.warning('device {}: - {}: {}'.format(device_id, key, value))
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


def ac_mon(jee, client, device_id):
    """Monitor an AC/HVAC device, showing higher-level information about
    its status such as its temperature and operation mode.
    """

    device = client.get_device(device_id)
    if device.type != wideq.DeviceType.AC:
        LOGGER.warning('This is not an AC device.')
        return

    ac = wideq.ACDevice(client, device)

    try:
        ac.monitor_start()
    except wideq.core.NotConnectedError:
        LOGGER.warning('Device not available.')
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


def set_temp(jee, client, device_id, temp):
    """Set the configured temperature for an AC or refrigerator device."""

    device = client.get_device(device_id)

    if device.type == wideq.client.DeviceType.AC:
        ac = wideq.ACDevice(client, _force_device(client, device_id))
        ac.set_fahrenheit(int(temp))
    elif device.type == wideq.client.DeviceType.REFRIGERATOR:
        refrigerator = wideq.RefrigeratorDevice(
            client, _force_device(client, device_id))
        refrigerator.set_temp_refrigerator_c(int(temp))
    else:
        raise UserError(
            'set-temp only suported for AC or refrigerator devices')


def set_temp_freezer(jee, client, device_id, temp):
    """Set the configured freezer temperature for a refrigerator device."""

    device = client.get_device(device_id)

    if device.type == wideq.client.DeviceType.REFRIGERATOR:
        refrigerator = wideq.RefrigeratorDevice(
            client, _force_device(client, device_id))
        refrigerator.set_temp_freezer_c(int(temp))
    else:
        raise UserError(
            'set-temp-freezer only suported for refrigerator devices')


def turn(jee, client, device_id, on_off):
    """Turn on/off an AC device."""

    ac = wideq.ACDevice(client, _force_device(client, device_id))
    ac.set_on(on_off == 'on')


def ac_config(jee, client, device_id):
    ac = wideq.ACDevice(client, _force_device(client, device_id))
    LOGGER.info(ac.supported_operations)
    LOGGER.info(ac.supported_on_operation)
    LOGGER.info(ac.get_filter_state())
    LOGGER.info(ac.get_mfilter_state())
    LOGGER.info(ac.get_energy_target())
    LOGGER.info(ac.get_power() + " watts")
    LOGGER.info(ac.get_outdoor_power() + " watts")
    LOGGER.info(ac.get_volume())
    LOGGER.info(ac.get_light())
    LOGGER.info(ac.get_zones())


EXAMPLE_COMMANDS = {
    'ls': ls,
    'mon': mon,
    'ac-mon': ac_mon,
    'set-temp': set_temp,
    'set-temp-freezer': set_temp_freezer,
    'turn': turn,
    'ac-config': ac_config,
}


def example_command(jee, client, cmd, args):
    func = EXAMPLE_COMMANDS.get(cmd)
    if not func:
        LOGGER.error("Invalid command: '%s'.\n"
                     "Use one of: %s", cmd, ', '.join(EXAMPLE_COMMANDS))
        return
    func(jee, client, *args)


def example(jee: jeedom, verbose: bool,
            cmd: str, args: List[str]) -> None:
    if verbose:
        wideq.set_log_level(logging.DEBUG)

    # Load the current state for the example.
    try:
        with open(STATE_FILE) as f:
            LOGGER.debug("State file found '%s'", os.path.abspath(STATE_FILE))
            state = json.load(f)
    except IOError:
        state = {}
        LOGGER.debug("No state file found (tried: '%s')",
                     os.path.abspath(STATE_FILE))

    client = wideq.Client.load(state)
    
    country = jee.config.byKey('LgCountry', 'lgthinq')
    language = jee.config.byKey('LgLanguage', 'lgthinq')
    auth = jee.config.byKey('LgAuthUrl', 'lgthinq')
    logUrl = jee.config.byKey('LgGateway', 'lgthinq')
    
    # display status config
    LOGGER.info( 'jeedom "{}" lgthinq country:{} language:{} auth URL:"{}"'
        .format( jee.config.byKey('name'), country, language, auth))

    if country:
        client._country = country
    if language:
        client._language = language
    if not auth:
        jee.config.save('LgGateway', gateway.oauth_url(), 'lgthinq')
        sys.exit('Missing configuration: auth URL')

    # Log in, if we don't already have an authentication.
    if not client._auth:
        client._auth = wideq.Auth.from_url(client.gateway, auth)

    # Loop to retry if session has expired.
    while True:
        try:
            example_command(jee, client, cmd, args)
            break

        except wideq.NotLoggedInError:
            LOGGER.info('Session expired.')
            client.refresh()

        except UserError as exc:
            LOGGER.error(exc.msg)
            sys.exit(1)

    # Save the updated state.
    state = client.dump()
    with open(STATE_FILE, 'w') as f:
        json.dump(state, f)
        LOGGER.debug("Wrote state file '%s'", os.path.abspath(STATE_FILE))


def main() -> None:
    """The main command-line entry point.
    """
    parser = argparse.ArgumentParser(
        description='Connector between the LG SmartThinQ API and Jeedom.'
    )
    parser.add_argument('cmd', metavar='CMD', nargs='?', default='ls',
                        help=f'one of: {", ".join(EXAMPLE_COMMANDS)}')
    parser.add_argument('args', metavar='ARGS', nargs='*',
                        help='subcommand arguments')

    parser.add_argument(
        '--ip', '-i',
        help=f'IP adress of jeedom (default: http://192.168.1.10)',
        default='http://192.168.1.10'
    )
    parser.add_argument(
        '--key', '-k',
        help=f'the jeedom API key',
        default=None
    )
    parser.add_argument(
        '--verbose', '-v',
        help='verbose mode to help debugging',
        action='store_true', default=False
    )

    args = parser.parse_args()
    if not args.key:
        LOGGER.error("Jeedom API key mandatory: argument -k")
        exit(1)

    if args.verbose:
        LOGGER.setLevel(logging.DEBUG)

    # command line:
    # python jeedom.py --ip http://192.168.1.25 --key kLbmBWVeQSqbhluECyycGEeGAXXZOahS
    LOGGER.info('python jeedom.py --ip {} --key {}'.format(args.ip, args.key))
    jee = jeedom(args.ip, args.key)
    example(jee, args.verbose, args.cmd, args.args)


if __name__ == '__main__':
    main()
