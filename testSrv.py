import time
from flask import Flask

api = Flask(__name__)

# starting datetime
starting = time.time()


# Definition of the routes.
@api.route("/")
def hello_world():
    """
    check if server is alive
    """
    return {
        "msg": "Hello World! This is the wideq-flask server, i'm alive :)",
        "starting": '{0.tm_year}/{0.tm_mon}/{0.tm_mday} \
                    at {0.tm_hour}:{0.tm_min}:{0.tm_sec}'
                    .format(time.localtime(starting)),
        "debug": True,
    }


api.run(host="0.0.0.0", debug=True)
