import argparse
import logging
import wideq
import os
import re
import sys
import time
import json

from pyJeedom import jeedom

LOGGER = logging.getLogger("jeedom.py")

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
    else: fail
    """
    global WClient, path_file
    
    path_file = (os.path.dirname(os.path.realpath(__file__)) +
        "/" + STATE_FILE)
    LOGGER.debug("Run from " + os.getcwd() + " save to " + 
        path_file)

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
                         type(ex), ex.args, str(ex))

    if WClient is None:
        LOGGER.error("no Wideq client found")

    return WClient


class jeedomConfig():
    """
    external and independant supplier for wideq client configuration
    use jeedom, required args are: IP and API key
    private properties:
    ip ( jeedom ip)
    key ( jeedom api key )
    jeedom ( the pyJeedom instance )
    _eqLogic ( list of jeedom objects )
    _client ( method to find and load wideq instance )
    """

    def __init__(self, ip, key):
        self.ip = ip
        self.key = key
        self.jeedom = jeedom(ip, key)
        self._eqLogic = {}
        self._client = None

    @property
    def client(self):
        if not self._client:
            self._client = getClient(self)
        return self._client

    @property
    def devices(self):
        try:
            devices = self.client.devices
        except wideq.core.NotLoggedInError:
            self.client.refresh()
            devices = self.client.devices
        return {device.id: device.__dict__ for device in devices}

    def _getKey(self, key):
        result = self.jeedom.config.byKey(key, 'lgthinq')
        if "error" in result:
            raise Exception(result["error"])
        return result

    def log(self, level):
        numeric_level = getattr(logging, level.upper(), None)
        if not isinstance(numeric_level, int):
            raise wideq.APIError(404, "Unknown log level {}".format(level))
        LOGGER.setLevel(logging.DEBUG)

    def getClient(self):
        """ask jeedom to retrieve config parameters
        to initiate wideq client instance
        """
        country = self._getKey('LgCountry')
        language = self._getKey('LgLanguage')
        auth = self._getKey('LgAuthUrl')

        # Your Jeedom name:
        LOGGER.debug('jeedom %s lgthinq country:%s language:%s auth URL:%s',
                     self._getKey('name'), country, language, auth)

        client = wideq.Client.load({})
        client._country = country
        client._language = language
        if auth:
            client._auth = wideq.Auth.from_url(client.gateway, auth)
        return client

    def gateway(self, country, language):
        """get the auth Url for country and market
        """
        if not re.compile(r"^[A-Z]{2,3}$").match(country):
            msg = "Country must be two or three letters" \
               " all upper case (e.g. US, NO, KR) got: '{}'".format(country)
            LOGGER.error(msg)
            raise wideq.APIError(404, msg)

        if not re.compile(r"^[a-z]{2,3}-[A-Z]{2,3}$").match(language):
            msg = "Language must be a combination of language" \
               " and country (e.g. en-US, no-NO, kr-KR)" \
               " got: '{}'".format(language)
            LOGGER.error(msg)
            raise wideq.APIError(404, msg)

        LOGGER.info("auth country=%s, lang=%s", country, language)

        client = getClient(self)
        client._country = country
        client._language = language
        return {'url': client.gateway.oauth_url()}

    def save(self, file):
        """
        dump wideq configuration data to json file
        """
        # Save the updated state.
        state = self.client.dump()
        if file == None:
            if path_file is None:
                LOGGER.warning("No path defined, save json to default path" +
                    os.cwd())
                file = STATE_FILE
            else:
                file = path_file
        with open(file, 'w') as f:
            json.dump(state, f)
            LOGGER.debug("Wrote state file '%s'", os.path.abspath(file))
        return {'save': file}

    @property
    def eqLogics(self):
        """
        ask jeedom for eqLogics configuration
        """
        if not self._eqLogic:
            result = self.jeedom.eqLogic.byType('lgthinq')
            LOGGER.debug("init %s eqLogic", len(result))
            for eq in result:
                self._eqLogic[eq['logicalId']] = eqLogic(eq, self.jeedom)
        return self._eqLogic

    def cmd(self, eqLogicId):
        """
        ask jeedom for commands configuration
        """
        result = self.jeedom.cmd.byEqLogicId(eqLogicId)
        return result

    def update(self, logicalId):
        """Monitor LG device, and update jeedom with result
        """
        try:
            data = self.mon(logicalId)
        except wideq.APIError as e:
            LOGGER.error(str(e))
        else:
            eq = self.eqLogics[logicalId]
            # list of every LG commands
            for key, value in data.items():
                # if jeedom has similar command:
                if eq.hasCommand(key):
                    # maj jeedom with new value
                    eq.event(key, value)
                else:
                    LOGGER.debug("no command {} in object {}"
                                 .format(key, eq.name))

    def mon(self, logicalId):
        """
        Monitor LG device and return json formatted information
        """
        if logicalId not in self.eqLogics:
            raise wideq.APIError(404, "no LG device for logicalId {}"
                                 .format(logicalId))

        eq = self.eqLogics[logicalId]
        # monitor eq element if enabled
        if eq.isEnable != '1':
            raise wideq.APIError(404, "device not active in jeedom "
                                 "configuration (logicalId {})"
                                 .format(logicalId))

        LOGGER.info('lgthinq id({}) {} \'{}\' ({}-{}) contains {} commands'
                    .format(eq.id, eq.name, eq.logicalId, eq.isVisible,
                            eq.isEnable, len(eq.commands)))

        try:
            device = self.client.get_device_obj(eq.logicalId)
        except wideq.core.NotLoggedInError:
            self.client.refresh()
            device = self.client.get_device_obj(eq.logicalId)

        if device is None:
            LOGGER.warning("no LG device for jeedom configuration {} id= {}"
                           .format(eq.name, eq.logicalId))
            raise wideq.APIError(404,
                                 "no LG device for jeedom configuration "
                                 "{} id= {}".format(eq.name, eq.logicalId))

        try:
            state = eq.mon(device)
        except wideq.core.NotLoggedInError:
            self.client.refresh()
            state = eq.mon(device)

        if state:
            return state.data
        else:
            raise wideq.APIError(404,
                                 'no monitoring data for {}'
                                 .format(logicalId))


class eqLogic():
    """
    this class contains jeedom eqLogic configuration and commands
    and real-time commands values
    """

    def __init__(self, json, jeedom):
        self.id = json['id']
        self.logicalId = json['logicalId']
        self.json = json
        self.jeedom = jeedom
        cmds = jeedom.cmd.byEqLogicId(json['id'])

        # commands with logicalId as the index
        self.commands = {}
        for cmd in cmds:
            self.commands[cmd['logicalId']] = cmd
        # commands values with jeedom id as the index
        self.values = {}

    def __getattr__(self, nom):
        if nom in self.json:
            return self.json[nom]
        else:
            LOGGER.warning('pas d\'attribut %s dans eqLogic %s',
                           nom, self.json['id'])

    def getCommand(self, name):
        if name in self.commands:
            return self.commands.get(name)
        else:
            LOGGER.warning('pas de commande %s dans eqLogic %s',
                           name, self.json['name'])

    def hasCommand(self, name):
        return name in self.commands

    def event(self, name, value):
        """
        update jeedom command if the value changed.
        name is the jeedom human command name
        value is the new monitored value
        """
        id = self.commands.get(name)['id']
        if id not in self.values or self.values[id] != value:
            # cache the new value
            self.values[id] = value
            # maj jeedom
            self.jeedom.cmd.event(id, value)
            LOGGER.debug("%s: maj %s = %s", self.name, name, value)

    def mon(self, device):
        """Monitor any device, return higher-level information about
        its status such as its temperature and operation mode.
        """
        try:
            device.monitor_start()
        except wideq.core.NotConnectedError:
            LOGGER.warning('device %s not connected', device.device.name)
            return

        try:
            for i in range(5):
                time.sleep(1)
                # poll returns some device status information
                state = device.poll()
                if state:
                    return state
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


def main() -> None:
    """
    The main command-line entry point.
    require jeedom IP and API key.
    optional id is the command id to monitor.
    """
    parser = argparse.ArgumentParser(
        description='Connector between the LG SmartThinQ API and Jeedom.'
    )

    parser.add_argument(
        '--ip', '-i',
        help='IP adress of jeedom (default: http://localhost)',
        default='http://localhost'
    )
    parser.add_argument(
        '--key', '-k',
        help='the jeedom API key',
        default=None
    )
    parser.add_argument(
        '--verbose', '-v',
        help='verbose mode to help debugging',
        action='store_true', default=False
    )
    parser.add_argument(
        '--id', '-j',
        help='The Jeedom Command Id to monitor. Optional, default '
             'is monitoring everything.',
        default=None
    )

    args = parser.parse_args()
    if not args.key:
        LOGGER.error("Jeedom API key mandatory: argument -k")
        exit(1)

    if args.verbose:
        LOGGER.setLevel(logging.DEBUG)
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    logging.basicConfig(stream=sys.stdout, level=log_level,
                        format='%(asctime)s - %(name)s - '
                               '%(levelname)s - %(message)s')

    # command line:
    # python jeedom.py --ip http://192.168.1.25
    # --key kLbmBWVeQSqbhluECyycGEeGAXXZOahS
    print('python jeedom.py --ip {} --key {}'.format(args.ip, args.key))
    jee = jeedomConfig(args.ip, args.key)

    client = jee.client
    client.refresh()
    # get all LG connected devices
    for device in client.devices:
        print(device, '{0.id}: {0.name} ({0.type.name} {0.model_id})'
              .format(device))

    if args.id:
        cmd = jee.cmd.byId(args.id)

    # Get all jeedom eqLogics:
    pluginEqlogics = jee.eqLogics
    for eq in pluginEqlogics.values():
        jee.update(eq.logicalId)


if __name__ == '__main__':
    main()
