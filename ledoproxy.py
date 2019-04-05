import requests
import json

class NoFlight(Exception):
    pass

class ProxyClient(object):
    def __init__(self, apiurl):
        if apiurl[-1] == '/':
            self._apiurl = apiurl[:-1]
        else:
            self._apiurl = apiurl

    def _http_request(self, query):
        headers = {}
        url = '%s/%s' % (self._apiurl, query)
        res = requests.get(url, headers=headers)
        return res.json()

    def get_flights(self):
        query = 'flights'
        res = self._http_request(query)

        try:
            return res['flights']
        except KeyError:
            raise NoFlight

    def get_flight(self, fltnr):
        query = 'flight/%s' % fltnr
        res = self._http_request(query)

        try:
            return res['flights']
        except KeyError:
            raise NoFlight

    def get_aircraft(self, acreg):
        query = 'aircraft/%s' % acreg
        res = self._http_request(query)

        try:
            return res['flights']
        except KeyError:
            raise NoFlight

