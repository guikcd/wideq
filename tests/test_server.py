import unittest
from flask import Flask, json, jsonify, request
from flask.logging import create_logger
from werkzeug.exceptions import HTTPException

import server

POLL_DATA = {
    'APCourse': '10',
    'DryLevel': '0',
    'Error': '0',
    'Initial_Time_H': '0',
    'Initial_Time_M': '58',
    'LoadLevel': '4',
    'OPCourse': '0',
    'Option1': '0',
    'Option2': '0',
    'Option3': '2',
    'PreState': '23',
    'Remain_Time_H': '0',
    'Remain_Time_M': '13',
    'Reserve_Time_H': '0',
    'Reserve_Time_M': '0',
    'RinseOption': '1',
    'SmartCourse': '51',
    'Soil': '0',
    'SpinSpeed': '5',
    'State': '30',
    'TCLCount': '15',
    'WaterTemp': '4',
}


class WideqServerTest(unittest.TestCase):
    """
    this is for testing some server features
    """

    def setUp(self):
        super().setUp()
        with open('./tests/fixtures/client.json') as fp:
            state = json.load(fp)
        self.client = Client.load(state)

        app = server.create_app()
        app.debug = True
        self.app = app.test_client()

    ###############
    #### tests ####
    ###############

    def test_main_page(self):
        response = self.app.get('/ping', follow_redirects=True)
        self.assertEqual(response.status_code, 200)


if __name__ == "__main__":
    unittest.main()
