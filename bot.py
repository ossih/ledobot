#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from telegram.ext import Updater, CommandHandler
import ledoproxy
import airport
import formatting
import ledotracker

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
tracker = ledotracker.TrackerClient(config['ledotracker']['url'])

updater = Updater(token=config['telegram']['token'])
dispatcher = updater.dispatcher

class CmdHandler(object):
    def __init__(self, dispatcher):
        self._commands = {}
        self._dispatcher = dispatcher

    def cmd(self, func):
        name = func.__name__
        if name.startswith('cmd_'):
            name = name.split('_', 1)[1]
        self._commands[name] = func

        self._dispatcher.add_handler(CommandHandler(name, func, pass_args=True))
        return func

    def get_cmds(self):
        return self._commands.keys()

    def get_helps(self):
        return dict((name, func.__doc__) for name, func in self._commands.items() if func.__doc__)

cmdhandler = CmdHandler(dispatcher)

@cmdhandler.cmd
def cmd_start(update, context):
    """Start usage.. Does nothing."""
    context.bot.sendMessage(chat_id=update.message.chat_id, text='You need /help?', parse_mode='Markdown')


@cmdhandler.cmd
def cmd_help(update, context):
    """Get help"""
    log_msg(update)
    args = context.args
    cmds = cmdhandler.get_cmds()
    helps = cmdhandler.get_helps()

    if len(args) == 0:
        rows = []
        for cmd in cmds:
            if cmd == 'start':
                continue
            if cmd in helps.keys():
                rows.append('/%s - %s' % (cmd, helps[cmd]))
            else:
                rows.append('/%s' % cmd)
        resp = '\n'.join(rows)

    elif args[0] in helps.keys():
        resp = helps[args[0]]

    else:
        resp = '??'

    context.bot.sendMessage(chat_id=update.message.chat_id, text=resp, parse_mode='Markdown')

@cmdhandler.cmd
def cmd_flight(update, context):
    """Get flight info"""
    log_msg(update)
    args = context.args
    try:
        if len(args) == 0:
            resp = 'Which flight?'
            context.bot.sendMessage(chat_id=update.message.chat_id, text=resp, parse_mode='Markdown')
            return

        fltnr = args[0].upper()
        try:
            for flight in ledoclient.get_flight(fltnr):
                fmt = formatting.FinaviaFormatter(flight)
                context.bot.sendMessage(chat_id=update.message.chat_id, text=fmt.to_text(), parse_mode='Markdown')
        except ledoproxy.NoFlight:
            resp = 'Flight %s not found' % fltnr
            context.bot.sendMessage(chat_id=update.message.chat_id, text=resp, parse_mode='Markdown')
            return

    except:
        traceback.print_exc()

@cmdhandler.cmd
def cmd_flights(update, context):
    """List flights with given prefix"""
    log_msg(update)
    args = context.args
    try:
        flights = ledoclient.get_flights()

        if len(args) > 0:
            prefix = args[0].upper()
            flights = [f for f in flights if f.startswith(prefix)]

        resp = '\n'.join(flights)

        if not flights:
            resp = 'No flights found'

        context.bot.sendMessage(chat_id=update.message.chat_id, text=resp, parse_mode='Markdown')

    except:
        traceback.print_exc()

@cmdhandler.cmd
def cmd_metar(update, context):
    """Get METAR by ICAO or IATA identifier"""
    log_msg(update)
    args = context.args
    try:
        if len(args) == 0:
            resp = '??'

        else:
            code = args[0].upper()

            try:
                resp = metar.get(code)
            except airport.NoData:
                resp = '%s not found' % code

        context.bot.sendMessage(chat_id=update.message.chat_id, text=resp, parse_mode='Markdown')

    except:
        traceback.print_exc()

@cmdhandler.cmd
def cmd_aircraft(update, context):
    """Get flights for given aircraft"""
    log_msg(update)
    args = context.args
    try:
        if len(args) == 0:
            resp = 'Which aircraft?'
            context.bot.sendMessage(chat_id=update.message.chat_id, text=resp, parse_mode='Markdown')
            return

        aircraft = args[0].upper()
        aircraft = aircraft.replace('-', '')
        try:
            for flight in ledoclient.get_aircraft(aircraft):
                fmt = formatting.FinaviaFormatter(flight)
                context.bot.sendMessage(chat_id=update.message.chat_id, text=fmt.to_text(), parse_mode='Markdown')
        except ledoproxy.NoFlight:
            resp = 'No flights found'
            context.bot.sendMessage(chat_id=update.message.chat_id, text=resp, parse_mode='Markdown')
            return

    except:
        traceback.print_exc()

@cmdhandler.cmd
def cmd_track(update, context):
    """Track departure and arrival of flight"""
    log_msg(update)
    args = context.args
    try:
        if len(args) == 0:
            resp = 'Which flight?'
            context.bot.sendMessage(chat_id=update.message.chat_id, text=resp, parse_mode='Markdown')
            return

        fltnr = args[0].upper()
        chatid = update.message.chat_id
        userdata = update.message.from_user.to_dict()
        if 'username' in userdata.keys():
            notify = '@%s' % userdata['username']
        else:
            notify = userdata['first_name']

        if chatid == userdata['id']:
            resp = tracker.track(fltnr, chatid)
        else:
            resp = tracker.track(fltnr, userdata['id'], chan=chatid, notify=notify)

        context.bot.sendMessage(chat_id=update.message.chat_id, text=resp['message'], parse_mode='Markdown')

    except:
        traceback.print_exc()

@cmdhandler.cmd
def cmd_untrack(update, context):
    """Stop tracking flight"""
    log_msg(update)
    args = context.args
    try:
        if len(args) == 0:
            resp = 'Which flight?'
            context.bot.sendMessage(chat_id=update.message.chat_id, text=resp, parse_mode='Markdown')
            return

        fltnr = args[0].upper()
        chatid = update.message.chat_id
        userdata = update.message.from_user.to_dict()

        if chatid == userdata['id']:
            resp = tracker.untrack(fltnr, chatid)
        else:
            resp = tracker.untrack(fltnr, userdata['id'], chan=chatid)

        context.bot.sendMessage(chat_id=update.message.chat_id, text=resp['message'], parse_mode='Markdown')

    except:
        traceback.print_exc()

updater.start_polling()
updater.idle()

