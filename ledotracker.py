import requests
import json

class TrackerClient(object):
    def __init__(self, trackerurl):
        self._trackerurl = trackerurl

    def track(self, fltnr, user, chan=None, notify=None):
        payload = {'fltnr': fltnr, 'user': user}
        if chan and notify:
            payload['chan'] = chan
            payload['notify'] = notify

        url = '%s/%s' % (self._trackerurl, 'track')
        res = requests.post(url, headers={'Content-Type': 'application/json'}, data=json.dumps(payload))
        return res.json()

    def untrack(self, fltnr, user, chan=None):
        payload = {'fltnr': fltnr, 'user': user}
        if chan:
            payload['chan'] = chan

        url = '%s/%s' % (self._trackerurl, 'untrack')
        res = requests.post(url, headers={'Content-Type': 'application/json'}, data=json.dumps(payload))
        return res.json()
