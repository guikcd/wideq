import ssl
import time
import argparse
import re
import uuid
import os.path
import logging
import requests
from flask import Flask, json, jsonify, request
from flask.logging import create_logger
from werkzeug.exceptions import HTTPException

import wideq

api = Flask(__name__)

STATE_FILE = 'wideq_state.json'
TOKEN_KEY = 'jeedom_token'

# state is the client global config
# state = {}
client = None
# the token value
token_value = ''
# starting datetime
starting = time.time()


@api.errorhandler(Exception)
def handle_error(e):
    code = 500
    if isinstance(e, HTTPException):
        code = e.code
    logging.debug(e, exc_info=True)
    return jsonify(error=str(e)), code


class InvalidUsage(Exception):
    """
    generic exception errorhandler
    """
    status_code = 400

    def __init__(self, message, status_code=None, payload=None):
        Exception.__init__(self)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.payload = payload

    def to_dict(self):
        """
        generate a message with value
        """
        rv = dict(self.payload or ())
        rv['message'] = self.message
        return rv


def check_headers(headers):
    """
    check authentication with access token from the header request.
    """
    if TOKEN_KEY not in headers:
        logging.debug('request without token ' + str(headers))
        raise InvalidUsage('No jeedom token.', status_code=401)
    if headers[TOKEN_KEY] != token_value:
        raise InvalidUsage('Invalid jeedom token ###' +  headers[TOKEN_KEY] + \
          '###'+ token_value +'###', status_code=401)

def Response(dico, code=200, mimetype='application/json'):
    """
    Response of this REST API is:
    'state'= 'ok' or 'error'
    'result' contains json encoded data
    'code' = error code (404 , 500, ...) or 200 if OK
    """
    state = ('ok' if code < 300 else 'error')
    r = jsonify(result=dico, state=state, code=code)
    r.status_code = code
    r.headers['Content-Type'] = mimetype
    return r


@api.errorhandler(InvalidUsage)
def handle_invalid_usage(error):
    """
    default error handler
    """
    logging.debug(error, exc_info=True)
    return Response(error.to_dict(), error.status_code)


@api.route('/ping', methods=['GET'])
def get_ping():
    """
    check if server is alive
    """
    logging.debug('ping token ' + str(token_value))
    return Response({'starting': starting, TOKEN_KEY: (token_value != '')})

@api.route('/log/<string:level>', methods=['GET', 'POST'])
def set_log(level):
    """
    change log level for application: [debug|info|warn|error]
    """
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
        raise InvalidUsage('Unknown Log level {}'.format(level) ,status_code=410)

    wideq.set_log_level(lvl)
    logging.setLevel(lvl)
    create_logger(api).setLevel(lvl)
    return Response({'log':level})


@api.route('/gateway/<string:country>/<string:language>', methods=['GET'])
def get_auth(country, language):
    """get the auth Url for country and market"""
    global client

    logging.debug('get auth with country %s and lang %s ', country, language)

    if not country:
        country = wideq.DEFAULT_COUNTRY

    country_regex = re.compile(r"^[A-Z]{2,3}$")
    if not country_regex.match(country):
        msg = "Country must be two or three letters" \
           " all upper case (e.g. US, NO, KR) got: '{}'".format(country)
        logging.error(msg)
        raise InvalidUsage(msg, 410)

    if not language:
        language = wideq.DEFAULT_LANGUAGE

    language_regex = re.compile(r"^[a-z]{2,3}-[A-Z]{2,3}$")
    if not language_regex.match(language):
        msg = "Language must be a combination of language" \
           " and country (e.g. en-US, no-NO, kr-KR)" \
           " got: '{}'".format(language)
        logging.error(msg)
        raise InvalidUsage(msg, 410)

    logging.info("auth country=%s, lang=%s", country, language)

    client = wideq.Client.load({}) # state vide = {}
    if country:
        client._country = country
    if language:
        client._language = language

    gateway = client.gateway
    login_url = gateway.oauth_url()
    # Save the updated state.
    # state = client.dump()

    return Response({'url':login_url})

@api.route('/auth', methods=['GET'])
def get_auth_default():
    logging.debug('get default auth')
    return get_auth(wideq.DEFAULT_COUNTRY, wideq.DEFAULT_LANGUAGE)

@api.route('/token/<path:token>', methods=['GET', 'POST'])
def get_token(token):
    """
    URL from LG login with the token
    """
    global client, token_value  # , state

    # client = wideq.Client.load(state)
    client._auth = wideq.Auth.from_url(client.gateway, token)
    # Save the updated state.
    # state = client.dump()
    # generate jeedom token
    token_value = str(uuid.uuid4())
    return Response({TOKEN_KEY: token_value})


#
#
#   list of available commands, requiere authentication with headers
#
#


@api.route('/save', methods=['GET'])
def get_save_default():
    """
    Save the updated state to a default json file
    """
    return get_save(STATE_FILE)

@api.route('/save/<string:file>', methods=['GET'])
def get_save(file):
    """
    Save the updated state to a local json file
    """
    check_headers(request.headers)
    with open(file, 'w') as wri:
        # add token_value
        backup = dict(client.dump()) # state
        backup[TOKEN_KEY] = token_value
        json.dump(backup, wri)
        logging.debug("Wrote state file '%s'", os.path.abspath(file))
    return Response({'config':backup, 'file':file})


@api.route('/ls', methods=['GET' ])
def get_ls():
    """
    List the user's devices.
    """
    global client

    logging.debug('request for ls: ' + str(request))
    check_headers(request.headers)

    # client = wideq.Client.load(state)
    client.refresh()

    # Loop to retry if session has expired.
    i = 0
    while i < 10:
        i += 1
        try:
            result = []
            for device in client.devices:
                logging.debug('{0.id}: {0.name} ({0.type.name} {0.model_id})'.format(device))
                result.append({'id':device.id, 'name':device.name,
                  'type':device.type.name, 'model':device.model_id})
            logging.debug(str(len(result)) + ' elements: ' + str(result))

            # Save the updated state.
            # state = client.dump()

            return Response(result)

        except wideq.NotLoggedInError:
            logging.info('Session expired.')
            client.refresh()

        except UserError as exc:
            logging.error(exc.msg)
            raise InvalidUsage(exc.msg, 401)

    raise InvalidUsage('Error, no response from LG cloud', 401)

@api.route('/mon/<device_id>', methods=['GET'])
def monitor(device_id):
    """Monitor any device, displaying generic information about its
    status.
    """

    check_headers(request.headers)

    # client = wideq.Client.load(state)
    device = client.get_device(device_id)
    model = client.model_info(device)

    with wideq.Monitor(client.session, device_id) as mon:
        try:
            i = 0
            while i < 10:
                i += 1
                data = mon.poll()
                if data:
                    try:
                        res = model.decode_monitor(data)
                    except ValueError:
                        print('status data: {!r}'.format(data))
                    else:
                        result = {}
                        for key, value in res.items():
                            try:
                                desc = model.value(key)
                            except KeyError:
                                print('- {}: {}'.format(key, value))
                            if isinstance(desc, wideq.EnumValue):
                                # print('- {}: {}'.format( key, desc.options.get(value, value) ))
                                result[key] = desc.options.get(value, value)
                            elif isinstance(desc, wideq.RangeValue):
                                # print('- {0}: {1} ({2.min}-{2.max})'.format( key, value, desc, ))
                                result[key] = value
                                result[key + '.min'] = desc.min
                                result[key + '.max'] = desc.max

                        return Response(result)

                time.sleep(1)
                print('Polling...')

        except KeyboardInterrupt:
            pass

    raise InvalidUsage('Error, no response from LG cloud', 401)



@api.route('/set/<command>/<device_id>/<value>', methods=['GET'])
def set_command(client, device_id, temp):
    """
    Set the configured command for an AC or refrigerator device.
    command is: temp, temp_freezer, turn
    """

    device = client.get_device(device_id)

    if command == 'temp':
        if device.type == wideq.client.DeviceType.AC:
            ac = wideq.ACDevice(client, _force_device(client, device_id))
            ac.set_fahrenheit(int(temp))
        elif device.type == wideq.client.DeviceType.REFRIGERATOR:
            refrigerator = wideq.RefrigeratorDevice(
                client, _force_device(client, device_id))
            refrigerator.set_temp_refrigerator_c(int(temp))
        else:
            raise raise InvalidUsage(
                'set-temp only suported for AC or refrigerator devices', 401)

    elif command == 'temp_freezer':
        if device.type == wideq.client.DeviceType.REFRIGERATOR:
            refrigerator = wideq.RefrigeratorDevice(
                client, _force_device(client, device_id))
            refrigerator.set_temp_freezer_c(int(temp))
        else:
            raise InvalidUsage(
                'set-temp-freezer only suported for refrigerator devices', 401)

    elif command == 'turn':
        _ac = wideq.ACDevice(client, _force_device(device_id))
        _ac.set_on(on_off == 'on')

    else:
        raise InvalidUsage('unsupported command: {}'.format(command), 401)

#
#
#   list of not available commands, TODO
#
#


def ac_mon(device_id):
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


def _force_device(device_id):
    """Look up a device in the client (using `get_device`), but raise
    InvalidUsage if the device is not found.
    """
    device = client.get_device(device_id)
    if not device:
        raise InvalidUsage('device "{}" not found'.format(device_id), 401)
    return device



def ac_config(device_id):
    """
    config for Air Climatized device
    """
    _ac = wideq.ACDevice(client, _force_device(device_id))
    print(_ac.get_filter_state())
    print(_ac.get_mfilter_state())
    print(_ac.get_energy_target())
    print(_ac.get_power(), " watts")
    print(_ac.get_outdoor_power(), " watts")
    print(_ac.get_volume())
    print(_ac.get_light())
    print(_ac.get_zones())


def _build_ssl_context(maximum_version=None, minimum_version=None):
    """Configure the default SSLContext with min and max version
    """
    if not hasattr(ssl, "SSLContext"):
        raise RuntimeError("httplib2 requires Python 3.2+ for ssl.SSLContext")

    # fix ssl.SSLError: [SSL: DH_KEY_TOO_SMALL] dh key too small (_ssl.c:1056)
    requests.packages.urllib3.util.ssl_.DEFAULT_CIPHERS += 'HIGH:!DH:!aNULL'
    try:
      requests.packages.urllib3.contrib.pyopenssl.DEFAULT_SSL_CIPHER_LIST += 'HIGH:!DH:!aNULL'
    except AttributeError:
      # no pyopenssl support used / needed / available
      pass

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

def main():
    """The main command-line entry point.
    """
    parser = argparse.ArgumentParser(
        description='REST API for the LG SmartThinQ wideq Lib.'
    )

    parser.add_argument(
        '--port', '-p', type=int,
        help='port for server (default: 5025)',
        default=5025
    )
    parser.add_argument(
        '--verbose', '-v',
        help='verbose mode to help debugging',
        action='store_true', default=False
    )

    args = parser.parse_args()

    if args.verbose:
        logLevel=logging.DEBUG
    else:
        logLevel=logging.INFO

    logging.basicConfig(level=logLevel)
    context = _build_ssl_context( 'TLSv1', 'TLSv1')
    logging.debug(
      'Starting {0} server at {1.tm_year}/{1.tm_mon}/{1.tm_mday} at {1.tm_hour}:{1.tm_min}:{1.tm_sec}'.format(
        'debug' if args.verbose else '', time.localtime(starting)))
    api.run(port=args.port, debug=args.verbose)


if __name__ == '__main__':
    main()
