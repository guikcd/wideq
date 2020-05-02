[![PyPI](https://img.shields.io/pypi/v/wideq.svg)](https://pypi.org/project/wideq/)
[![CircleCI](https://circleci.com/gh/sampsyo/wideq.svg?style=svg)](https://circleci.com/gh/sampsyo/wideq)

WideQ
=====

A library for interacting with the "LG SmartThinq" system, which can control heat pumps and such. I reverse-engineered the API from their mobile app.

To try out the API, there is a simple command-line tool included here, called `example.py`.
To use it, provide it with a country and language code via the `-c` and `-l` flags, respectively:

    $ python3 example.py -c US -l en-US

LG accounts seem to be associated with specific countries, so be sure to use the one with which you originally created your account.
For Korean, for example, you'd use `-c KR -l ko-KR`.

On first run, the script will ask you to log in with your LG account.
Logging in with Google does not seem to work, but other methods (plain email & password, Facebook, and Amazon) do. 

By default, the example just lists the devices associated with your account.
You can also specify one of several other commands:

* `ls`: List devices (the default).
* `mon <ID>`: Monitor a device continuously, printing out status information until you type control-C. Provide a device ID obtained from listing your devices.
* `ac-mon <ID>`: Like `mon`, but only for AC devices---prints out specific climate-related information in a more readable form.
* `set-temp <ID> <TEMP>`: Set the target temperature for an AC device.
* `turn <ID> <ONOFF>`: Turn an AC device on or off. Use "on" or "off" as the second argument.
* `ac-config <ID>`: Print out some configuration information about an AC device.


There is a small HTTP Flask server wideqServer.py, using the following syntax:

    $ python3 wideqServer.py

Then, with another command-line, you can send some basic HTTP requests, using wget command:

* `wget -qO- http://127.0.0.1:5025/ping` : check if the server is alive with ping
* `wget -qO- http://127.0.0.1:5025/log/debug` : change the log level
* `wget -qO- http://127.0.0.1:5025/gateway/FR/fr-FR` : initialize the client gateway with country and language, the response send you the URL to login with your LG account
* `wget -qO- http://127.0.0.1:5025/token/https%3A%2F%2Ffr.m.lgaccount.com%2Flogin%2FiabClose%3Faccess_token%3D<access token>%26refresh_token%3D<refresh token>%26oauth2_backend_url%3Dhttps%3A%2F%2Fgb.lgeapi.com%2F` : get back the redirect LG accoutn URL and ***apply URL-encoding*** for the next command:
* `wget -qO- http://127.0.0.1:5025/ls` : get the list of connected devices
* `wget -qO- https://127.0.0.1:5025/mon/33d29e50-7196-11e7-a90d-b4e62a6453c5` : get monitoring values for one device

Default port is 5025, but you can change it with -p arg when launching the server.


Credits
-------

This is by [Adrian Sampson][adrian].
The license is [MIT][].
I also made a [Home Assistant component][hass-smartthinq] that uses wideq.

[hass-smartthinq]: https://github.com/sampsyo/hass-smartthinq
[adrian]: https://github.com/sampsyo
[mit]: https://opensource.org/licenses/MIT
