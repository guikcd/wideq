"""
A simple Flask-server implementation of wideq lib to expose
most common operations of the LG wideq lib
See also https://www.python-boilerplate.com/flask
"""
import os
import logging
import time

from flask import Flask, jsonify

TOKEN_KEY = 'jeedom_token'

def create_app(config=None):
    app = Flask(__name__)

    # the token value
    token_value = ''
    # starting datetime
    starting = time.time()

    # See http://flask.pocoo.org/docs/latest/config/
    app.config.update(dict(DEBUG=True))
    app.config.update(config or {})

    # Definition of the routes. Put them into their own file. See also
    # Flask Blueprints: http://flask.pocoo.org/docs/latest/blueprints
    @app.route("/")
    def hello_world():
        return "Hello World"

    @app.route("/foo/<someId>")
    def foo_url_arg(someId):
        return jsonify({"echo": someId})

    @app.route('/ping', methods=['GET'])
    def get_ping():
        """
        check if server is alive
        """
        logging.debug('ping token ' + str(token_value))
        return jsonify({'starting': starting, TOKEN_KEY: (token_value != '')})

    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app = create_app()
    app.run(host="0.0.0.0", port=port)
