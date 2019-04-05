import json
import requests
import re

class NoSuchAirport(Exception):
    pass

class NoData(Exception):
    pass

class Airports(object):
    def __init__(self):
        self._airports = {}
        self.load_airports()

    def load_airports(self):
        with open('airports.json', 'r') as f:
            self._airports = json.loads(f.read())

    def get(self, icao):
        if not icao in self._airports.keys():
            raise NoSuchAirport

        return self._airports[icao]

    def get_by_iata(self, iata):
        for _, airport in self._airports.items():
            if not airport['iata']:
                continue

            if airport['iata'] == iata:
                return airport

        # Not found
        raise NoSuchAirport


class Metar(object):
    def __init__(self):
        self._baseurl = 'http://tgftp.nws.noaa.gov/data/observations/metar/stations/{}.TXT'
        self._rex_icao = re.compile('^[A-Z0-9]{4}$')
        self._rex_iata = re.compile('^[A-Z]{3}$')
        self._airports = Airports()



    def get(self, code):
        if self._rex_icao.match(code):
            icao = code
        elif self._rex_iata.match(code):
            iata = code
            try:
                aport = self._airports.get_by_iata(iata)
                icao = aport['icao']
            except NoSuchAirport:
                raise NoData

        else:
            raise NoData

        req = requests.get(self._baseurl.format(icao))

        if req.status_code == 200:
            lines = req.text.splitlines()
            metar = lines[1]

            return metar

        else:
            raise NoData

