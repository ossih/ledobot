#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from telegram.ext import Updater, CommandHandler
import ledoproxy
import airport

import re
import sys
import json
import time
import random
import datetime
import requests

import traceback

import logging
logging.basicConfig(level=logging.INFO, format='%(levelname)-8s %(name)s %(message)s')
logger = logging.getLogger('ledobot')

with open('config.json', 'r') as f:
    config = json.loads(f.read())

def log_msg(update):
    m = update.message
    text = m.text
    userdata = m.from_user.to_dict()

    if 'username' in userdata.keys():
        sender = userdata['username']
    elif 'last_name' in userdata.keys():
        sender = '%s %s' % (userdata['first_name'], userdata['last_name'])
    else:
        sender = userdata['first_name']

    if m.chat.type == 'group':
        chat = 'group:%s' % m.chat.title
    else:
        chat = m.chat.type

    prefix = 'msg:%s' % chat
    logger.info(' :: '.join((prefix, sender, text)))


ledoclient = ledoproxy.ProxyClient(config['ledoproxy']['url'])
airports = airport.Airports()
metar = airport.Metar()

updater = Updater(token=config['telegram']['token'])
dispatcher = updater.dispatcher

def start(bot, update):
    bot.sendMessage(chat_id=update.message.chat_id, text='yrlbnry')

class NoData(Exception):
    pass

def build_path(flight, arrival=False):
    rpoints = []
    rex = re.compile('^route_[0-9]+$')
    for key in flight.keys():
        if rex.match(key):
            if flight[key]:
                rpoints.append(flight[key])

    apt = flight['h_apt']

    if arrival:
        return rpoints + [apt]
    else:
        return [apt] + rpoints

def parse_time(sdt):
    dt = datetime.datetime.strptime(sdt, '%Y-%m-%dT%H:%M:%SZ')
    utc = dt.replace(tzinfo=datetime.timezone.utc)

    return utc

def get_codes(flight):
    codes = []
    rex = re.compile('^cflight_[0-9]+$')
    for key in flight.keys():
        if rex.match(key):
            if flight[key]:
                codes.append(flight[key])

    codes.sort()
    return codes

def fmt_name(flight, arrival=False):
    fltnr = flight['fltnr']

    path = build_path(flight, arrival)
    fpath = ' - '.join(path)
    fname = '%s %s' % (fltnr, fpath)

    return fname

def fmt_time(flight, arrival=False):
    prefix = arrival and 'Arrival' or 'Departure'
    sdt = flight['sdt']
    utc = parse_time(sdt)
    dt = utc.astimezone()

    ftime = '%s: %s' % (prefix, dt.strftime('%d.%m. %H:%M'))

    return ftime

def fmt_aircraft(flight):
    acreg = flight['acreg']
    actype = flight['actype']

    aircraft = 'Aircraft: %s' % actype
    if acreg:
        aircraft = '%s (%s)' % (aircraft, acreg)

    return aircraft

def fmt_gate(flight):
    gate = flight['gate']

    if not gate:
        raise NoData

    fgate = 'Gate: %s' % gate

    return fgate

def fmt_park(flight):
    gate = flight['gate']
    park = flight['park']

    if not park or gate == park:
        raise NoData

    fpark = 'Stand: %s' % park

    return fpark

def fmt_belt(flight):
    blt = flight['bltarea']

    if not blt:
        raise NoData

    fbelt = 'Baggage claim: %s' % blt

    return fbelt

def fmt_chin(flight):
    chkarea = flight['chkarea']
    chkdsk1 = flight['chkdsk_1']
    chkdsk2 = flight['chkdsk_2']

    if not chkarea:
        raise NoData

    fchin = 'Check-in: Area %s' % chkarea

    if chkdsk1 and chkdsk2:
        fchin = '%s (Desk %s - %s)' % (fchin, chkdsk1, chkdsk2)

    return fchin

def fmt_codes(flight):
    codelist = get_codes(flight)

    if not codelist:
        raise NoData

    codes = ', '.join(codelist)
    codes = 'Alternative codes: %s' % codes
    return codes

def fmt_status(flight):
    prt = flight['prt']

    if not prt:
        raise NoData

    fstatus = 'Status: %s' % prt

    return fstatus

def fmt_est(flight):
    est = flight['est_d']

    if not est:
        raise NoData

    utc = parse_time(est)
    dt = utc.astimezone()

    fest = 'Estimated: %s' % dt.strftime('%d.%m. %H:%M')

    return fest

def fmt_act(flight):
    act = flight['act_d']

    if not act:
        raise NoData

    utc = parse_time(act)
    dt = utc.astimezone()

    fact = 'Actual: %s' % dt.strftime('%d.%m. %H:%M')

    return fact

def fmt_arr(flight):
    lines = []
    lines.append(fmt_name(flight, arrival=True))
    lines.append(fmt_time(flight, arrival=True))
    lines.append(fmt_aircraft(flight))

    try:
        lines.append(fmt_gate(flight))
    except NoData:
        pass

    try:
        lines.append(fmt_park(flight))
    except NoData:
        pass

    try:
        lines.append(fmt_belt(flight))
    except NoData:
        pass

    try:
        lines.append(fmt_codes(flight))
    except NoData:
        pass

    try:
        lines.append(fmt_status(flight))
    except NoData:
        pass

    try:
        lines.append(fmt_est(flight))
        lines.append(fmt_act(flight))
    except NoData:
        pass


    resp = '\n'.join(lines)
    return resp

def fmt_dep(flight):
    lines = []
    lines.append(fmt_name(flight))
    lines.append(fmt_time(flight))
    lines.append(fmt_aircraft(flight))

    try:
        lines.append(fmt_gate(flight))
    except NoData:
        pass

    try:
        lines.append(fmt_park(flight))
    except NoData:
        pass

    try:
        lines.append(fmt_chin(flight))
    except NoData:
        pass

    try:
        lines.append(fmt_codes(flight))
    except NoData:
        pass

    try:
        lines.append(fmt_status(flight))
    except NoData:
        pass

    try:
        lines.append(fmt_est(flight))
        lines.append(fmt_act(flight))
    except NoData:
        pass

    resp = '\n'.join(lines)
    return resp


def cmd_flight(bot, update, args):
    log_msg(update)
    try:
        if len(args) == 0:
            resp = 'Which flight?'
            bot.sendMessage(chat_id=update.message.chat_id, text=resp)
            return

        fltnr = args[0].upper()
        try:
            for flight in ledoclient.get_flight(fltnr):
                if flight['arrival']:
                    resp = fmt_arr(flight)
                    bot.sendMessage(chat_id=update.message.chat_id, text=resp)
                else:
                    resp = fmt_dep(flight)
                    bot.sendMessage(chat_id=update.message.chat_id, text=resp)
        except ledoproxy.NoFlight:
            resp = 'Flight %s not found' % fltnr
            bot.sendMessage(chat_id=update.message.chat_id, text=resp)
            return

    except:
        traceback.print_exc()

def cmd_flights(bot, update, args):
    log_msg(update)
    try:
        flights = ledoclient.get_flights()

        if len(args) > 0:
            prefix = args[0].upper()
            flights = [f for f in flights if f.startswith(prefix)]

        resp = '\n'.join(flights)

        if not flights:
            resp = 'No flights found'

        bot.sendMessage(chat_id=update.message.chat_id, text=resp)

    except:
        traceback.print_exc()

def cmd_metar(bot, update, args):
    try:
        log_msg(update)
        if len(args) == 0:
            resp = '??'

        else:
            code = args[0].upper()

            try:
                resp = metar.get(code)
            except airport.NoData:
                resp = '%s not found' % code

        bot.sendMessage(chat_id=update.message.chat_id, text=resp)

    except:
        traceback.print_exc()

def cmd_aircraft(bot, update, args):
    try:
        if len(args) == 0:
            resp = 'Which aircraft?'
            bot.sendMessage(chat_id=update.message.chat_id, text=resp)
            return

        aircraft = args[0].upper()
        aircraft = aircraft.replace('-', '')
        try:
            for flight in ledoclient.get_aircraft(aircraft):
                if flight['arrival']:
                    resp = fmt_arr(flight)
                    bot.sendMessage(chat_id=update.message.chat_id, text=resp)
                else:
                    resp = fmt_dep(flight)
                    bot.sendMessage(chat_id=update.message.chat_id, text=resp)
        except ledoproxy.NoFlight:
            resp = 'No flights found'
            bot.sendMessage(chat_id=update.message.chat_id, text=resp)
            return

    except:
        traceback.print_exc()


dispatcher.add_handler(CommandHandler('start', start))
dispatcher.add_handler(CommandHandler('metar', cmd_metar, pass_args=True))
dispatcher.add_handler(CommandHandler('flight', cmd_flight, pass_args=True))
dispatcher.add_handler(CommandHandler('flights', cmd_flights, pass_args=True))
dispatcher.add_handler(CommandHandler('aircraft', cmd_aircraft, pass_args=True))

updater.start_polling()
updater.idle()

