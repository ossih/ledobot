import re
import datetime

class NoData(Exception):
    pass

def parse_time(sdt):
    dt = datetime.datetime.strptime(sdt, '%Y-%m-%dT%H:%M:%SZ')
    utc = dt.replace(tzinfo=datetime.timezone.utc)

    return utc

class FinaviaFormatter(object):
    def __init__(self, flight):
        self._flight = flight
        self._rex_route = re.compile('^route_[0-9]+$')
        self._rex_codes = re.compile('^cflight_[0-9]+$')

    def build_path(self):
        rpoints = []
        for key in self._flight.keys():
            if self._rex_route.match(key):
                if self._flight[key]:
                    rpoints.append(self._flight[key])

        apt = self._flight['h_apt']

        if self._flight['arrival']:
            return rpoints + [apt]
        else:
            return [apt] + rpoints

    def get_codes(self):
        codes = []
        for key in self._flight.keys():
            if self._rex_codes.match(key):
                if self._flight[key]:
                    codes.append(self._flight[key])

        codes.sort()
        return codes

    def fmt_name(self):
        fltnr = self._flight['fltnr']

        path = self.build_path()
        fpath = ' - '.join(path)
        fname = '%s %s' % (fltnr, fpath)

        return fname

    def fmt_time(self):
        action = self._flight['arrival'] and 'Arrival' or 'Departure'
        sdt = self._flight['sdt']
        utc = parse_time(sdt)
        dt = utc.astimezone()

        ftime = '%s: %s' % (action, dt.strftime('%d.%m. %H:%M'))

        return ftime

    def fmt_aircraft(self):
        acreg = self._flight['acreg']
        actype = self._flight['actype']

        if acreg:
            aircraft = 'Aircraft: %s (%s)' % (actype, acreg)
        else:
            aircraft = 'Aircraft: %s' % actype

        return aircraft

    def fmt_gate(self):
        gate = self._flight['gate']

        if not gate:
            raise NoData

        fgate = 'Gate: %s' % gate
        return fgate

    def fmt_park(self):
        gate = self._flight['gate']
        park = self._flight['park']

        if not park or gate == park:
            raise NoData

        fpark = 'Stand: %s' % park
        return fpark

    def fmt_belt(self):
        if not 'bltarea' in self._flight.keys() or not self._flight['bltarea']:
            raise NoData

        fbelt = 'Baggage claim: %s' % self._flight['bltarea']
        return fbelt

    def fmt_chin(self):
        if not 'chkarea' in self._flight.keys() or not self._flight['chkarea']:
            raise NoData

        chkarea = self._flight['chkarea']
        chkdsk1 = self._flight['chkdsk_1']
        chkdsk2 = self._flight['chkdsk_2']

        if chkdsk1 and chkdsk2:
            fchin = 'Check-in: Area %s (Desk %s - %s)' % (chkarea, chkdsk1, chkdsk2)
        else:
            fchin = 'Check-in: Area %s' % chkarea

        return fchin

    def fmt_codes(self):
        codelist = self.get_codes()

        if not codelist:
            raise NoData

        codes = 'Alternative codes: %s' %  ', '.join(codelist)
        return codes

    def fmt_status(self):
        prt = self._flight['prt']

        if not prt:
            raise NoData

        fstatus = 'Status: %s' % prt
        return fstatus

    def fmt_est(self):
        est = self._flight['est_d']

        if not est:
            raise NoData

        utc = parse_time(est)
        dt = utc.astimezone()

        fest = 'Estimated: %s' % dt.strftime('%d.%m. %H:%M')
        return fest

    def fmt_act(self):
        act = self._flight['act_d']

        if not act:
            raise NoData

        utc = parse_time(act)
        dt = utc.astimezone()

        fact = 'Actual: %s' % dt.strftime('%d.%m. %H:%M')
        return fact

    def to_text(self):
        lines = []
        funcs = [
                self.fmt_name,
                self.fmt_time,
                self.fmt_aircraft,
                self.fmt_gate,
                self.fmt_park,
                self.fmt_belt,
                self.fmt_chin,
                self.fmt_codes,
                self.fmt_status,
                self.fmt_est,
                self.fmt_act
                ]

        for func in funcs:
            try:
                lines.append(func())
            except NoData:
                continue


        resp = '\n'.join(lines)
        return resp

