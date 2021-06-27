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
    if debug:
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
        result = app['auth'](token, None, None)
        return jsonify(result)

    @api.route("/<cmd>/<arg1>/<arg2>/<arg3>")
    def any_route3(cmd, arg1, arg2, arg3):
        """
        Generic route definition with command and 2 optionals arguments
        """
        if cmd in app and callable(app[cmd]):
            LOGGER.debug(f'{cmd} with arg {arg1} / {arg2} / {arg3}')
            try:
                return jsonify(app[cmd](arg1, arg2, arg3))
            except APIError as e:
                rep = {'message': e.message, 'code': e.code}
                if debug:
                    rep['trace'] = traceback.format_exc()
                LOGGER.error(rep)
                abort(make_response(jsonify(rep), 404))
            except Exception as e:
                rep = {'message': str(e), 'code': 500}
                if debug:
                    rep['trace'] = traceback.format_exc()
                    # raise e  # for Flask debugger display
                LOGGER.error(rep)
                abort(make_response(jsonify(rep), 500))
        else:
            abort(make_response(jsonify(
                message=f'command "{cmd}" not found or not callable'),
                404))

    @api.route("/<cmd>/<arg1>/<arg2>")
    def any_route2(cmd, arg1, arg2):
        return any_route3(cmd, arg1, arg2, None)

    @api.route("/<cmd>/<arg1>")
    def any_route1(cmd, arg1):
        return any_route3(cmd, arg1, None, None)

    @api.route("/<cmd>")
    def any_route0(cmd):
        return any_route3(cmd, None, None, None)

    return api


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

    print(' * python jeedom srv.py --ip {} --key {}'.format(args.ip,
                                                            args.key))
    # jee = jeedom.jeedomConfig(args.ip, args.key)

    # mapping between HTTP words and lgthinq methods :
    funcs = {
        'ls': lambda u, v, w: lgthinq.ls(),
        'info': lambda u, v, w: lgthinq.info(u),
        'mon': lambda u, v, w: lgthinq.mon(u),
        'log': lambda u, v, w: lgthinq.log(u),
        'gateway': lambda u, v, w: lgthinq.gateway(u, v),
        'auth': lambda u, v, w: lgthinq.auth(u),
        'save': lambda u, v, w: lgthinq.save(file=u),
        'set': lambda u, v, w: lgthinq.set(u, v, w),
    }
    api = create_app(funcs, debug=args.verbose)
    api.run(host="0.0.0.0", port=args.port, debug=args.verbose)
