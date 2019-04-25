#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from telegram.ext import Updater, CommandHandler
import ledoproxy
import airport
import formatting

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
    bot.sendMessage(chat_id=update.message.chat_id, text='yrlbnry', parse_mode='Markdown')

def cmd_flight(bot, update, args):
    log_msg(update)
    try:
        if len(args) == 0:
            resp = 'Which flight?'
            bot.sendMessage(chat_id=update.message.chat_id, text=resp, parse_mode='Markdown')
            return

        fltnr = args[0].upper()
        try:
            for flight in ledoclient.get_flight(fltnr):
                fmt = formatting.FinaviaFormatter(flight)
                bot.sendMessage(chat_id=update.message.chat_id, text=fmt.to_text(), parse_mode='Markdown')
        except ledoproxy.NoFlight:
            resp = 'Flight %s not found' % fltnr
            bot.sendMessage(chat_id=update.message.chat_id, text=resp, parse_mode='Markdown')
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

        bot.sendMessage(chat_id=update.message.chat_id, text=resp, parse_mode='Markdown')

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

        bot.sendMessage(chat_id=update.message.chat_id, text=resp, parse_mode='Markdown')

    except:
        traceback.print_exc()

def cmd_aircraft(bot, update, args):
    try:
        if len(args) == 0:
            resp = 'Which aircraft?'
            bot.sendMessage(chat_id=update.message.chat_id, text=resp, parse_mode='Markdown')
            return

        aircraft = args[0].upper()
        aircraft = aircraft.replace('-', '')
        try:
            for flight in ledoclient.get_aircraft(aircraft):
                fmt = formatting.FinaviaFormatter(flight)
                bot.sendMessage(chat_id=update.message.chat_id, text=fmt.to_text(), parse_mode='Markdown')
        except ledoproxy.NoFlight:
            resp = 'No flights found'
            bot.sendMessage(chat_id=update.message.chat_id, text=resp, parse_mode='Markdown')
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

