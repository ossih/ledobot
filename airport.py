import json

class NoSuchAirport(Exception):
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
