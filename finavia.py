#!/usr/bin/env python3

import requests
import xmltodict
import pprint

class NoSuchFlight(Exception):
    pass

class FinaviaAPI:
    def __init__(self, app_id, app_key):
        self._api_url = 'https://api.finavia.fi/flights/public/v0/flights/all/all'
        self._app_id = app_id
        self._app_key = app_key

    def update(self):
        headers = {'app_id': self._app_id, 'app_key': self._app_key}
        res = requests.get(self._api_url, headers=headers)

        data = xmltodict.parse(res.text)
        flights = data['flights']

        self._arrs = {}
        self._deps = {}

        for flight in flights['arr']['body']['flight']:
            fltnr = flight.get('fltnr')
            if fltnr in self._arrs.keys():
                self._arrs[fltnr].append(flight)
            else:
                self._arrs[fltnr] = [flight]

        for flight in flights['dep']['body']['flight']:
            fltnr = flight.get('fltnr')
            if fltnr in self._deps.keys():
                self._deps[fltnr].append(flight)
            else:
                self._deps[fltnr] = [flight]


    def con_dump(self):
        pp = pprint.PrettyPrinter(indent=2)
        pp.pprint(self._arrs)
        pp.pprint(self._deps)

    def get_arr(self, fltnr):
        if fltnr in self._arrs.keys():
            return self._arrs[fltnr]
        else:
            raise NoSuchFlight

    def get_dep(self, fltnr):
        if fltnr in self._deps.keys():
            return self._deps[fltnr]
        else:
            raise NoSuchFlight

    def get_arrs(self):
        return self._arrs.keys()

    def get_deps(self):
        return self._deps.keys()


