#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from telegram.ext import Updater, CommandHandler
import ledoproxy
import formatting

import json
import time
import threading
import bottle
import dictdiffer
import traceback

import logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)-8s %(name)s %(message)s')
logger = logging.getLogger('ledotracker')

with open('config.json', 'r') as f:
    config = json.loads(f.read())


ledoclient = ledoproxy.ProxyClient(config['ledoproxy']['url'])

updater = Updater(token=config['telegram']['token'])

class TrackingFailed(Exception):
    pass

class Tracker(threading.Thread):
    def __init__(self):
        super().__init__()
        self._is_running = False
        self._tracked_flights = {}

    def run(self):
        self._is_running = True
        while self._is_running:
            logger.debug('Checking flights needing updates')
            abandoned = []
            for fltnr, flight in self._tracked_flights.items():
                if flight.needs_update():
                    logger.debug('Invoking update for flight %s' % fltnr)
                    flight.update_status()
                    if flight.is_abandoned():
                        abandoned.append(fltnr)

            for fltnr in abandoned:
                logger.debug('Invoking delete for flight %s' % fltnr)
                del self._tracked_flights[fltnr]


            time.sleep(1)

    def stop(self):
        self._is_running = False
        return

    def add_tracker(self, fltnr, user, chan=None, notify=None):
        if not fltnr in self._tracked_flights.keys():
            try:
                flights = ledoclient.get_flight(fltnr)
            except ledoproxy.NoFlight:
                raise TrackingFailed('Flight %s not found' % fltnr)

            # Remove flights that are gone - arrivals not supported yet
            flights = [f for f in flights if not f['arrival'] and f['prt'] not in ['Departed', 'Cancelled']]
            if not flights:
                raise TrackingFailed('No upcoming flights with code %s' % fltnr)

            # Only first is interesting
            flight = flights[0]

            logger.info('Adding flight %s to tracker.' % fltnr)
            try:
                self._tracked_flights[fltnr] = TrackedFlight(flight)
            except:
                traceback.print_exc()
                raise TrackingFailed('General error occurred. See syslog for details.')

        self._tracked_flights[fltnr].add_sub(user, chan, notify)

        return


class TrackedFlight(object):
    def __init__(self, flight):
        self._state = flight
        self._fltnr = flight['fltnr']
        self._sdate = flight['sdate']
        self._priv_subs = []
        self._chan_subs = {}


        self.set_next_update()

    def needs_update(self):
        return time.time() >= self._next_update

    def update_status(self):
        try:
            flights = ledoclient.get_flight(self._fltnr)
            flight = [f for f in flights if f['sdate'] == self._state['sdate'] and f['arrival'] == self._state['arrival']][0]
        except:
            logger.info('Flight %s disppeared. Cleaning..' % self._fltnr)
            self._priv_subs = []
            self._chan_subs = {}
            return

        diff = list(dictdiffer.diff(self._state, flight))
        if diff:
            self.send_notifies(flight, diff)
            self._state = flight

        self.set_next_update()
        return

    def set_next_update(self):
        self._next_update = time.time() + 30
        return

    def send_notifies(self, flight, diff):
        fmt = formatting.FinaviaFormatter(flight)
        to_send = False
        lines = []
        lines.append(fmt.fmt_name())
        lines.append(fmt.fmt_time())
        lines.append('')
        lines.append('**NEW INFO**')
        for ctype, cvalue, change in diff:
            if ctype != 'change':
                continue
            interesting = {
                    'aircraft': 'fmt_aircraft',
                    'acreg': 'fmt_aircraft',
                    'gate': 'fmt_gate',
                    'park': 'fmt_park',
                    'prm': 'fmt_status',
                    'est_d': 'fmt_est',
                    'act_d': 'fmt_act'
                    }
            if not cvalue in interesting.keys():
                continue
            attr = interesting[cvalue]
            try:
                line = getattr(fmt, attr)()
                lines.append(line)
                to_send = True
            except:
                continue

        if to_send:
            text = '\n'.join(lines)
            for user in self._priv_subs:
                self.send_notify(user, text)

            for chan, users in self._chan_subs.items():
                to_notify = []
                for user, notify in users:
                    notstr = '[%s](tg://user?id=%s)' % (notify, user)
                    to_notify.append(notstr)
                notify_row = ' '.join(to_notify)
                ctext = '%s\n%s' % (notify_row, text)
                self.send_notify(chan, ctext)

    def send_notify(self, chatid, text):
        updater.bot.sendMessage(chat_id=chatid, text=text, parse_mode='Markdown')

    def is_abandoned(self):
        return not self._priv_subs and not self._chan_subs

    def add_sub(self, user, chan=None, notify=None):
        if not chan:
            if user in self._priv_subs:
                raise TrackingFailed('You are already tracking flight %s' % self._fltnr)
            else:
                self._priv_subs.append(user)

        else:
            if not chan in self._chan_subs.keys():
                self._chan_subs[chan] = []
            if user in map(lambda x:x[0], self._chan_subs[chan]):
                raise TrackingFailed('You are already tracking flight %s' % self._fltnr)
            else:
                self._chan_subs[chan].append((user, notify))

@bottle.route('/track', method='POST')
def r_track():
    payload = bottle.request.json

    if not 'fltnr' in payload.keys():
        return bottle.HTTPResponse(json.dumps({'status': 'error', 'message': 'Flight number is mandatory'}), status=500)
    if not 'user' in payload.keys():
        return bottle.HTTPResponse(json.dumps({'status': 'error', 'message': 'User ID is mandatory'}), status=500)

    if 'chan' in payload.keys():
        if not 'notify' in payload.keys():
            return bottle.HTTPResponse(json.dumps({'status': 'error', 'message': 'Notify name is mandatory when using channel'}), status=500)
        try:
            tracker.add_tracker(payload['fltnr'], payload['user'], chan=payload['chan'], notify=payload['notify'])
            return bottle.HTTPResponse(json.dumps({'status': 'success', 'message': 'Tracker added'}))
        except TrackingFailed as e:
            return bottle.HTTPResponse(json.dumps({'status': 'error', 'message': str(e)}), status=500)

    else:
        try:
            tracker.add_tracker(payload['fltnr'], (payload['user']))
            return bottle.HTTPResponse(json.dumps({'status': 'success', 'message': 'Tracker added'}))
        except TrackingFailed as e:
            return bottle.HTTPResponse(json.dumps({'status': 'error', 'message': str(e)}), status=500)




def add_all():
    flights = ledoclient.get_flights()
    for fltnr in flights:
        try:
            # Channel as user :D For spam :D
            tracker.add_tracker(fltnr, config['telegram']['testchan'], None)
        except TrackingFailed as e:
            print(e)

if __name__ == '__main__':
    try:
        tracker = Tracker()
        #add_all()
        tracker.start()
        bottle.run(host='0.0.0.0', port=8421)
    finally:
        tracker.stop()
