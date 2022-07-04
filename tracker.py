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
import datetime

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
        self._stopflag = threading.Event()
        self._tracked_flights = {}

    def run(self):
        while not self._stopflag.wait(timeout=1):
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
        self._stopflag.set()
        self.join()
        return

    def add_tracker(self, fltnr, user, chan=None, notify=None):
        if not fltnr in self._tracked_flights.keys():
            try:
                flights = ledoclient.get_flight(fltnr)
            except ledoproxy.NoFlight:
                raise TrackingFailed('Flight %s not found' % fltnr)
            except ledoproxy.ConnectionError:
                raise TrackingFailed('Connection error')

            # Remove flights that are gone
            flights = [f for f in flights if f['prt'] not in ['Departed', 'Landed', 'Cancelled']]
            if not flights:
                raise TrackingFailed('No upcoming flights with code %s' % fltnr)

            deps = list(filter(lambda x: not x['arrival'], flights))
            arrs = list(filter(lambda x: x['arrival'], flights))

            now = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
            deps_until = now + datetime.timedelta(hours=24)
            arrs_until = deps_until

            dep = None
            arr = None

            if deps:
                pdep = deps[0]
                deptime = formatting.parse_time(pdep['sdt'])
                if deptime < deps_until:
                    dep = pdep
                    arrs_until = deptime + datetime.timedelta(hours=24)

            if arrs:
                parr = arrs[0]
                arrtime = formatting.parse_time(parr['sdt'])
                if arrtime < arrs_until:
                    arr = parr

            # If tracking arrival after being departed, wrong departure may track
            if dep and arr:
                if formatting.parse_time(dep['sdt']) > formatting.parse_time(arr['sdt']):
                    dep = None

            logger.info('Adding flight %s to tracker.' % fltnr)
            try:
                self._tracked_flights[fltnr] = TrackedFlight(fltnr, dep=dep, arr=arr)
            except:
                traceback.print_exc()
                raise TrackingFailed('General error occurred. See syslog for details.')

        self._tracked_flights[fltnr].add_sub(user, chan, notify)

        return


class TrackedFlight(object):
    def __init__(self, fltnr, dep, arr):
        self._fltnr = fltnr
        self._dep = dep
        self._arr = arr
        self._priv_subs = []
        self._chan_subs = {}


        self.set_next_update()

    def needs_update(self):
        return time.time() >= self._next_update

    def update_status(self):
        try:
            flights = ledoclient.get_flight(self._fltnr)
        except ledoproxy.NoFlight:
            logger.info('Flight %s disppeared. Cleaning..' % self._fltnr)
            self._priv_subs = []
            self._chan_subs = {}
            return
        except ledoproxy.ConnectionError:
            logger.error('Could not get flight status. Skipping this round for %s' % self._fltnr)
            return


        if self._dep:
            deps = [f for f in flights if f['sdate'] == self._dep['sdate'] and not f['arrival']]
            if deps:
                dep = deps[0]
                diff = list(dictdiffer.diff(self._dep, dep))
                if diff:
                    self.send_notifies(self._dep, dep, diff)
                    self._dep = dep
            else:
                self._dep = None

        if self._arr:
            arrs = [f for f in flights if f['sdate'] == self._arr['sdate'] and f['arrival']]
            if arrs:
                arr = arrs[0]
                diff = list(dictdiffer.diff(self._arr, arr))
                if diff:
                    self.send_notifies(self._arr, arr, diff)
                    self._arr = arr
            else:
                self._arr = None

        if not self._dep and not self._arr:
            logger.info('Flight %s completed. Cleaning..' % self._fltnr)
            self._priv_subs = []
            self._chan_subs = {}
            return

        self.set_next_update()
        return

    def set_next_update(self):
        self._next_update = time.time() + 30
        return

    def send_notifies(self, old, new, diff):
        interesting = {
                'aircraft': 'fmt_aircraft',
                'acreg': 'fmt_aircraft',
                'gate': 'fmt_gate',
                'park': 'fmt_park',
                'prm': 'fmt_status',
                'est_d': 'fmt_est',
                'act_d': 'fmt_act',
                'bltarea': 'fmt_belt'
        }

        fmt_o = formatting.FinaviaFormatter(old)
        fmt_n = formatting.FinaviaFormatter(new)
        to_send = False
        lines = []
        lines.append(fmt_o.fmt_name())
        lines.append(fmt_o.fmt_time())
        if old['est_d']:
            lines.append(fmt_o.fmt_est())
        lines.append('')
        lines.append('**NEW INFO**')
        for ctype, cvalue, change in diff:
            if ctype != 'change':
                continue
            if not cvalue in interesting.keys():
                continue
            if cvalue == 'est_d' and old['est_d'] and new['est_d']:
                oldtime = formatting.parse_time(old['est_d'])
                newtime = formatting.parse_time(new['est_d'])
                if abs(oldtime - newtime) < datetime.timedelta(seconds=60):
                    logger.debug('Skipping estimate spam for %s' % self._fltnr)
                    continue

            attr = interesting[cvalue]
            try:
                line = getattr(fmt_n, attr)()
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

                # Send initial flight info when used privately
                if self._dep:
                    fmt = formatting.FinaviaFormatter(self._dep)
                    updater.bot.sendMessage(chat_id=user, text=fmt.to_text(), parse_mode='Markdown')

                if self._arr:
                    fmt = formatting.FinaviaFormatter(self._arr)
                    updater.bot.sendMessage(chat_id=user, text=fmt.to_text(), parse_mode='Markdown')

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
