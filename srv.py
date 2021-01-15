import sys
import argparse
import logging
import time
import lgthinq
import traceback

from flask import Flask, abort, jsonify, make_response
from wideq import APIError

LOGGER = logging.getLogger(__name__)


def create_app(app, debug=False):
    api = Flask(__name__)

    # starting datetime
    starting = time.time()

    # See http://flask.pocoo.org/docs/latest/config/
    api.config.update(dict(DEBUG=debug))

    @api.route("/")
    @api.route("/ping")
    def root():
        """
        check if server is alive
        """
        auth = lgthinq.check()
        msg = ("Hello World! This is the wideq-flask server, "
               "i'm alive :) auth " + ("ok" if auth else "ko"))
        return jsonify({
            "message": msg,
            "starting": '{0.tm_year}/{0.tm_mon}/{0.tm_mday} at {0.tm_hour}: '
            '{0.tm_min}:{0.tm_sec}'.format(time.localtime(starting)),
            "debug": debug,
            "auth": auth,
        })

    @api.route('/token/<path:token>', methods=['GET', 'POST'])
    def get_token(token):
        """
        URL from LG login with the token
        """
        # put token into current client auth configuration
        # WClient()._auth = core.Auth.from_url(WClient().gateway, token)
        app['auth'](token, None)
        return jsonify({'token': 'TRUE'})

    @api.route('/log/<log>')
    def route_set_log(log):
        """
        Change log level for this server
        """
        set_log(log)
        return jsonify({'log': log})

    @api.route("/<cmd>/<arg1>/<arg2>")
    def any_route2(cmd, arg1, arg2):
        """
        Generic route definition with command and 2 optionals arguments
        """
        if cmd in app and callable(app[cmd]):
            LOGGER.debug('{} with arg {} and {}'.format(cmd, arg1, arg2))
            try:
                return jsonify(app[cmd](arg1, arg2))
            except APIError as e:
                rep = {'message': e.message, 'code': e.code}
                if debug:
                    rep['trace'] = traceback.format_exc()
                LOGGER.error(str(e))
                abort(make_response(jsonify(rep), 404))
            except Exception as e:
                rep = {'message': str(e)}
                LOGGER.error(e)
                if debug:
                    rep['trace'] = traceback.format_exc()
                    # raise e  # for Flask debugger display
                abort(make_response(jsonify(rep), 500))
        else:
            abort(make_response(jsonify(
                message='command "{}" not found or not callable'.format(cmd)),
                404))

    @api.route("/<cmd>/<arg1>")
    def any_route1(cmd, arg1):
        return any_route2(cmd, arg1, None)

    @api.route("/<cmd>")
    def any_route0(cmd):
        return any_route2(cmd, None, None)

    return api


def set_log(log):
    levels = {
        'critical': logging.CRITICAL,
        'error': logging.ERROR,
        'warn': logging.WARNING,
        'warning': logging.WARNING,
        'info': logging.INFO,
        'debug': logging.DEBUG
    }
    level = levels.get(log.lower())
    if level is None:
        raise ValueError(
            f"log level given: {log}"
            f" -- must be one of: {' | '.join(levels.keys())}")
    logging.basicConfig(stream=sys.stdout,
                        format='%(asctime)s:%(levelname)s:%(message)s',
                        level=level)
    LOGGER.setLevel(level)
    return {'log': level}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='REST API for the LG SmartThinQ wideq Lib.'
    )

    parser.add_argument(
        '--ip', '-i',
        help='IP adress of jeedom (default: http://localhost)',
        default='http://localhost'
    )
    parser.add_argument(
        '--key', '-k', help='the jeedom API key',
        default=None, required=True
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
    set_log('debug' if args.verbose else 'info')

    print(' * python jeedom srv.py --ip {} --key {}'.format(args.ip,
                                                            args.key))
    # jee = jeedom.jeedomConfig(args.ip, args.key)

    funcs = {
        'ls': lambda u, v: lgthinq.ls(),
        'info': lambda u, v: lgthinq.info(u),
        'mon': lambda u, v: lgthinq.mon(u),
        'log': lambda u, v: lgthinq.log(u),
        'gateway': lambda u, v: lgthinq.gateway(u, v),
        'auth': lambda u, v: lgthinq.auth(u),
        'save': lambda u, v: lgthinq.save(u),
        'health': lambda u, v: lgthinq.health(),
    }
    api = create_app(funcs, debug=args.verbose)
    api.run(host="0.0.0.0", port=args.port, debug=args.verbose)
