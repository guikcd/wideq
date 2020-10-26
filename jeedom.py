import argparse
import logging
import wideq
import os
import sys
import time

from pyJeedom import jeedom

LOGGER = logging.getLogger("jeedom.py")

# global
WClient = None
STATE_FILE = 'wideq_state.json'

def getClient(supplier = None):
    """
    The global common method to initialize wideq client.
    First, use the global variable
    Second, search for the local json file
    Third, try to ask for an external configuration with the supplier
    else: fail
    """
    global WClient
    
    if WClient is None:
        # Load the current state for the example.
        try:
            with open(STATE_FILE) as f:
                LOGGER.debug("State file found '%s'", os.path.abspath(STATE_FILE))
                WClient = wideq.Client.load(json.load(f))
        except IOError:
            LOGGER.debug("No state file found (tried: '%s')",
                         os.path.abspath(STATE_FILE))
    
    if WClient is None and not supplier is None:
        try:
            LOGGER.debug("Get wideq client with external supplier '%s'", supplier)
            WClient = supplier.getClient()
        except Exception as ex:
            LOGGER.error("Cannot get wideq client with external supplier: '%s'", ex.msg)

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
    """
    def __init__(self, ip, key):
        self.ip = ip
        self.key = key
        self.jeedom = jeedom(ip, key)
        self._eqLogic = {}

    def _getKey(self, key):
        return self.jeedom.config.byKey(key, 'lgthinq')

    def getClient(self):
        country = self._getKey('LgCountry')
        language = self._getKey('LgLanguage')
        auth = self._getKey('LgAuthUrl')

        #Your Jeedom name:
        print( 'jeedom {} lgthinq country:{} language:{} auth URL:{}'.format( self._getKey('name'), country, language, auth))

        WClient = wideq.Client.load({})
        WClient._country = country
        WClient._language = language
        WClient._auth = wideq.Auth.from_url(WClient.gateway, auth)
        return WClient

    def eqLogics(self):
        """
        ask jeedom for eqLogics configuration
        """
        if not self._eqLogic:
            result = self.jeedom.eqLogic.byType('lgthinq')
            LOGGER.debug("init {} eqLogic".format( len(result)))
            for eq in result:
                self._eqLogic[eq['logicalId']] = eqLogic(eq, self.jeedom)
        return self._eqLogic
        
    def cmd(self, eqLogicId):
        """
        ask jeedom for commands configuration
        """
        result = self.jeedom.cmd.byEqLogicId(eqLogicId)
        # if self.cmd is None:
            # for cmd in result:
        return result


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
            LOGGER.warning('pas d\'attribut {} dans eqLogic {}'.format(nom, self.json['id']))

    def getCommand(self, name):
        if name in self.commands:
            return self.commands.get(name)
        else:
            LOGGER.warning('pas de commande {} dans eqLogic {}'.format(name, self.json['name']))
    
    def hasCommand(self, name):
        return name in self.commands

    # update jeedom command if the value changed
    def event(self, name, value):
        # jee.cmd.event(915, 'coucou')
        id = self.commands.get(name)['id']
        if not id in self.values or not self.values[id] == value:
            # cache the new value
            self.values[id] = value
            # ma jeedom
            self.jeedom.cmd.event(id, value)
            LOGGER.info("{}: maj {} = {}".format(self.name, name, value))
        
    
def getDevice(client, device_id):
    """
    switch the required Device object definition, according to device type
    """
    mapping = {
        wideq.DeviceType.AC: wideq.ACDevice,
        wideq.DeviceType.KIMCHI_REFRIGERATOR: wideq.RefrigeratorDevice,
        wideq.DeviceType.DISHWASHER: wideq.DishWasherDevice,
        wideq.DeviceType.DRYER : wideq.DryerDevice,
        wideq.DeviceType.WASHER : wideq.WasherDevice,
    }

    deviceInfo = client.get_device( device_id)
    if deviceInfo is None:
        return None
    if deviceInfo.type in mapping:
        return mapping.get(deviceInfo.type)(client, deviceInfo)
    LOGGER.info('pas de classe spécifique pour {} (modèle {})'.format(deviceInfo.name, deviceInfo.type))
    return Device(client, deviceInfo)


def mon(device):
    """Monitor any device, return higher-level information about
    its status such as its temperature and operation mode.
    """

    try:
        device.monitor_start()
    except wideq.core.NotConnectedError:
        LOGGER.warning('device %s not connected'.format(device))
        return

    try:
        for i in range(5):
            time.sleep(1)
            # poll returns some device status information
            state = device.poll()
            if state:
                return state
            else:
                print("no state for ", device, state)

    except KeyboardInterrupt:
        pass
    finally:
        device.monitor_stop()

  
def main() -> None:
    """The main command-line entry point.
    """
    parser = argparse.ArgumentParser(
        description='Connector between the LG SmartThinQ API and Jeedom.'
    )

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
    
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # command line:
    # python jeedom.py --ip http://192.168.1.25 --key kLbmBWVeQSqbhluECyycGEeGAXXZOahS
    print('python jeedom.py --ip {} --key {}'.format(args.ip, args.key))
    jee = jeedomConfig(args.ip, args.key)
    
    client = getClient(jee)
    client.refresh()
    for device in client.devices:
        print(device, '{0.id}: {0.name} ({0.type.name} {0.model_id})'.format(device))

    #Get all its eqLogics:
    pluginEqlogics = jee.eqLogics()
    for eq in pluginEqlogics.values():

        # monitor eq element if enabled
        if eq.isEnable == '1':
            nbCmds = len(jee.jeedom.cmd.byEqLogicId(eq.id))
            LOGGER.debug('lgthinq id({}) {} \'{}\' ({}-{}) contient {} commandes'.format(eq.id,
                eq.name, eq.logicalId, eq.isVisible, eq.isEnable, nbCmds))
            
            device = getDevice( client, eq.logicalId)
            if device is None:
                LOGGER.warning("no LG device for jeedom configuration {} id= {}".format(eq.name, eq.logicalId))
            else:
                state = mon( device)
                if state:
                    # list of every jeedom commands
                    for key, value in state.data.items():
                        if eq.hasCommand(key):
                            # maj jeedom with new value
                            cmd = eq.getCommand(key)
                            eq.event(key, value)
                        else:
                            LOGGER.debug("no command {} in object {}".format(key, eq.name))
    
    
if __name__ == '__main__':
    main()
