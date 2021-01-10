#!/usr/bin/env python3

import wideq
import json
import argparse
import os.path
import logging
import time
from typing import List

LOGGER = logging.getLogger(__name__)

# global
WClient = None
STATE_FILE = 'wideq_state.json'
# full path & file for json state file
path_file = None


def getClient(supplier=None):
    """
    The global common method to initialize wideq client.
    First, use the global variable
    Second, search for the local json file
    Third, try to ask for an external configuration with the supplier
    else: init new empty wideq client object
    """
    global WClient, path_file

    path_file = (os.path.dirname(os.path.realpath(__file__))
                 + "/" + STATE_FILE)
    LOGGER.debug("Run from " + os.getcwd() + " save to "
                 + path_file)

    if WClient is None:
        # Load the current state for the example.
        try:
            with open(path_file) as f:
                LOGGER.info("State file found '%s'",
                            os.path.abspath(path_file))
                WClient = wideq.Client.load(json.load(f))
        except IOError:
            LOGGER.debug("No state file found (tried: '%s')",
                         os.path.abspath(path_file))

    if WClient is None and supplier is not None:
        try:
            LOGGER.debug("Get wideq client with external supplier '%s'",
                         supplier)
            WClient = supplier.getClient()
        except Exception as ex:
            LOGGER.error("Cannot get wideq client with external "
                         "supplier: '%s' '%s' '%s'",
                         type(ex), ex.args, str(ex),
                         exc_info=True, stack_info=True)

    if WClient is None:
        LOGGER.info("no Wideq client was found, created a new one.")
        WClient = wideq.Client.load({})

    return WClient


def save(client):
    """
    Save the updated client state.
    """
    state = client.dump()
    with open(path_file, "w") as f:
        json.dump(state, f)
    LOGGER.debug("Wrote state file '%s'", os.path.abspath(path_file))
    return state


def gateway(country, language):
    """
    Init new wideq client gateway
    """
    client = getClient()
    client._country = country
    client._language = language
    save(client)
    return gateway.oauth_url()


def auth(auth):
    """
    authenticate with callback url
    """
    client = getClient()
    client._auth = wideq.Auth.from_url(gateway, auth)
    if client._auth is None:
        return False
    else:
        save(client)
        return True


def check():
    """
    Check correct LG authentication
    """
    client = getClient()
    return client._auth is not None


def ls():
    """
    List every LG connected device
    """
    data = []
    for device in get_device():
        data.append({'id': device.id, 'name': device.name,
                     'type': device.type.name, 'model': device.model_id})
    return data


def get_device(id=None):
    """
    Search for a devbice by ID. if ID is None, then return every device
    """
    client = getClient()
    try:
        result = client.devices
    except wideq.APIError:
        client.refresh()
        result = client.devices
    if id is None:
        return result
    for dev in result:
        if dev.id == id:
            return dev
    return None


def mon(id):
    """
    Monitor any device, displaying generic information about its status.
    """
    client = getClient()
    client.refresh()
    device = client.get_device_obj(id)
    if device is None:
        return {'code': 404, 'message': f'device {id} not found'}
    if isinstance(device, wideq.ACDevice):
        return ac_mon(device)
    else:
        return gen_mon(device)


def gen_mon(device):
    """
    Monitor any device except AC device, return higher-level information about
    its status such as its temperature and operation mode.
    """
    try:
        device.monitor_start()
    except wideq.core.NotConnectedError:
        msg = f'device {device.device.name} not connected'
        LOGGER.warning(msg)
        return {'code': 404, 'message': msg}

    try:
        for i in range(5):
            time.sleep(1)
            # poll returns some device status information
            state = device.poll()
            if state:
                return repr(state.data)
                return {'name': state.name, 'temp_cur': state.temp_cur_f,
                        'temp_cfg': state.temp_cfg_f,
                        'fan': state.fan_speed.name,
                        'state': 'on' if state.is_on else 'off'
                        }
            else:
                LOGGER.debug("no state for %s (%s) try again (%s)",
                             device.device.name, device.device.type, i)
        LOGGER.warning('timeout after 5 try, device %s %s unreachable',
                       device.device.name, device.device.type)

    except KeyboardInterrupt:
        LOGGER.info('keyboard interruption')
        pass
    finally:
        device.monitor_stop()


def ac_mon(ac):
    """
    Monitor an AC/HVAC device, showing higher-level information about
    its status such as its temperature and operation mode.
    """
    try:
        ac.monitor_start()
    except wideq.core.NotConnectedError:
        print("Device not available.")
        return

    try:
        while True:
            time.sleep(1)
            state = ac.poll()
            if state:
                print(
                    "{1}; "
                    "{0.mode.name}; "
                    "cur {0.temp_cur_f}°F; "
                    "cfg {0.temp_cfg_f}°F; "
                    "fan speed {0.fan_speed.name}".format(
                        state, "on" if state.is_on else "off"
                    )
                )
                return repr(state.data)
            else:
                print("no state. Wait 1 more second.")

    except KeyboardInterrupt:
        pass
    finally:
        ac.monitor_stop()


def example(verbose: bool,
            cmd: str, args: List[str]) -> None:
    if verbose:
        wideq.set_log_level(logging.DEBUG)

    # Load the current state for the example.
    client = getClient()

    # Save the updated state.
    save(client)


def main() -> None:
    """
    The main command-line entry point.
    search for json config to request LG cloud
    """
    parser = argparse.ArgumentParser(
        description='Connector for the LG SmartThinQ API.'
    )
    parser.add_argument('cmd', metavar='CMD', nargs='?', default='ls',
                        help=f'one of: {", ".join(None)}')
    parser.add_argument('args', metavar='ARGS', nargs='*',
                        help='subcommand arguments')
    parser.add_argument(
        '--verbose', '-v',
        help='verbose mode to help debugging',
        action='store_true', default=False
    )

    args = parser.parse_args()
    if args.verbose:
        LOGGER.setLevel(logging.DEBUG)

    example(args.verbose, args.cmd, args.args)


if __name__ == '__main__':
    main()
