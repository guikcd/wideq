"""
A simple Flask-server implementation of wideq lib to expose
most common operations of the LG wideq lib
See also https://www.python-boilerplate.com/flask
"""
import logging
import time
import ssl
import requests 
import re
import os.path

from werkzeug.exceptions import HTTPException
from flask import Flask, jsonify, json
from flask.logging import create_logger

from . import client, core  
        
  
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
        logging.error(message)

    def to_dict(self):
        """
        generate a message with value
        """
        rv = dict(self.payload or ())
        rv['message'] = self.message
        return rv


def create_app(config=None, debug=False):
    api = Flask(__name__)

    # starting datetime
    starting = time.time()

    # See http://flask.pocoo.org/docs/latest/config/
    api.config.update(dict(DEBUG=debug))
    api.config.update(config or {})


    @api.errorhandler(Exception)
    def handle_error(e):
        """
        any server error
        """
        code = 500
        if isinstance(e, HTTPException):
            code = e.code
        logging.error(e, exc_info=True)
        return {"error": str(e)}, code

    @api.errorhandler(InvalidUsage)
    def handle_invalid_usage(error):
        """
        default error handler
        """
        logging.warning(error, exc_info=True)
        return Response(error.to_dict(), error.status_code)

    def Response(dico, code=200):
        """
        Response of this REST API is:
        'state'= 'ok' or 'error'
        'result' contains json encoded data
        'code' = error code (404 , 500, ...) or 200 if OK
        """
        state = ('ok' if code < 300 else 'error')
        r = jsonify(result=dico, state=state, code=code)
        r.status_code = code
        r.headers['Content-Type'] = 'application/json'
        return r


    # Definition of the routes.
    @api.route("/")
    def hello_world():
        """
        check if server is alive
        """
        return {
            "msg": "Hello World! This is the wideq-flask server, i'm alive :)",
            "starting": '{0.tm_year}/{0.tm_mon}/{0.tm_mday} at {0.tm_hour}:{0.tm_min}:{0.tm_sec}'.format(time.localtime( starting)),
            "debug": debug,
        }


    @api.route('/ping', methods=['GET'])
    def get_ping():
        return hello_world()


    @api.route('/log/<string:level>', methods=['GET', 'POST'])
    def set_log(level):
        """
        change log level for application: [debug|info|warn|error]
        """
        numeric_level = getattr(logging, level.upper(), None)
        if not isinstance(numeric_level, int):
            raise InvalidUsage('Unknown Log level {}'.format(level) ,status_code=410)
        core.set_log_level(numeric_level)
        create_logger(api).setLevel(numeric_level)
        return Response({'log':level.upper()})


    @api.route('/gateway/<string:country>/<string:language>', methods=['GET'])
    def get_auth(country, language):
        """get the auth Url for country and market"""

        logging.info("auth country=%s, lang=%s", country, language)
        
        if not country:
            country = core.DEFAULT_COUNTRY

        country_regex = re.compile(r"^[A-Z]{2,3}$")
        if not country_regex.match(country):
            msg = "Country must be two or three letters" \
               " all upper case (e.g. US, NO, KR) got: '{}'".format(country)
            raise InvalidUsage(msg, 410)

        if not language:
            language = core.DEFAULT_LANGUAGE

        language_regex = re.compile(r"^[a-z]{2,3}-[A-Z]{2,3}$")
        if not language_regex.match(language):
            msg = "Language must be a combination of language" \
               " and country (e.g. en-US, no-NO, kr-KR)" \
               " got: '{}'".format(language)
            raise InvalidUsage(msg, 410)

        _client = WClient().load({}) # init singleton
        print("auth", country, language, _client)
        if _client:
            gateway = _client.gateway

        return Response({'url':gateway.oauth_url()})


    @api.route('/auth', methods=['GET'])
    def get_auth_default():
        """get default init auth url"""
        return get_auth(core.DEFAULT_COUNTRY, core.DEFAULT_LANGUAGE)


    @api.route('/token/<path:token>', methods=['GET', 'POST'])
    def get_token(token):
        """
        URL from LG login with the token
        """
        WClient()._auth = core.Auth.from_url(WClient().gateway, token)
        return Response({'token': 'TRUE'})


    @api.route('/save', methods=['GET'])
    def get_save():
        """
        Save the updated state as json data
        """
        return Response({'config':dict(WClient().dump())})


    @api.route('/ls', methods=['GET' ])
    def get_ls():
        """
        List the user's devices.
        """
        WClient().refresh()
        # Loop to retry if session has expired.
        for i in range(10):
            try:
                result = []
                for device in WClient().devices:
                    logging.debug('{0.id}: {0.name} ({0.type.name} {0.model_id})'.format(device))
                    result.append({'id':device.id, 'name':device.name,
                      'type':device.type.name, 'model':device.model_id})
                logging.debug(str(len(result)) + ' elements: ' + str(result))
                return Response(result)

            except NotLoggedInError:
                logging.info('Session expired. Auto refresh.')
                WClient().refresh()

            except UserError as exc:
                logging.error(exc.msg)
                raise InvalidUsage(exc.msg, 401)

        raise InvalidUsage('Error, no response from LG cloud', 401)


    @api.route('/mon/<dev_id>', methods=['GET'])
    def monitor(dev_id):
        """Monitor any device, displaying generic information about its
        status.
        """
        logging.debug("monitor {}".format(dev_id))

        try:
            device = WClient().get_device(dev_id)
            model = WClient().model_info(device)
        except NotLoggedInError as err:
            logging.error('mon {} NotLoggedInError: refresh session and try again. ({})'.format(dev_id, err))
            WClient().refresh();
            device = WClient().get_device(dev_id)
            model = WClient().model_info(device)
        except APIError as err:
            if err.code == 9003:
                logging.error('mon {} APIError: refresh session and try again. ({})'.format(dev_id, err))
                WClient().refresh();
                device = WClient().get_device(dev_id)
                model = WClient().model_info(device)

        with Monitor(WClient().session, dev_id) as mon:
            for i in range(10):
                data = mon.poll()
                if data:
                    try:
                        res = model.decode_monitor(data)
                    except ValueError:
                        logging.error('status data: {!r}'.format(data))
                    else:
                        result = {}
                        for key, value in res.items():
                            try:
                                desc = model.value(key)
                            except KeyError:
                                logging.warn('KeyError - {}: {}'.format(key, value))
                                result[key] = value
                            if isinstance(desc, EnumValue):
                                # print('- {}: {}'.format( key, desc.options.get(value, value) ))
                                result[key] = desc.options.get(value, value)
                            elif isinstance(desc, RangeValue):
                                # print('- {0}: {1} ({2.min}-{2.max})'.format( key, value, desc, ))
                                result[key] = value
                                result[key + '.min'] = desc.min
                                result[key + '.max'] = desc.max

                        return Response(result)

                time.sleep(1)
                logging.debug('Polling... {}'.format(i))

        raise InvalidUsage('Error, no response from LG cloud', 401)


    def _build_ssl_context(maximum_version=None, minimum_version=None):
        """
        Configure the default SSLContext with min and max version
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

    context = _build_ssl_context( 'TLSv1', 'TLSv1')
    logging.basicConfig(filename='lgthinq.log', format='%(asctime)s:%(levelname)s:%(message)s',
        level= logging.DEBUG if debug else logging.INFO)
    logging.debug(
      'Starting {0} server at {1.tm_year}/{1.tm_mon}/{1.tm_mday} at {1.tm_hour}:{1.tm_min}:{1.tm_sec}'.format(
        'debug' if debug else '', time.localtime( starting)))

    return api

