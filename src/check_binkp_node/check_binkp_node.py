#!/usr/bin/env python3
import argparse
import nagiosplugin
from datetime import datetime, timezone
from pprint import pprint
from construct import Int8ub, Struct, this, Bytes, GreedyRange
import time
import socket
import dateparser

__version__ = '0.1'

CONN_TIMEOUT = 10
READ_TIMEOUT = 3

# The v1.0 BINK Protocol spec:
# https://github.com/pgul/binkd/blob/master/doc/binkp10-en.txt
# Of course, I am not implementing an actual BINKP client...
binkp10format = Struct(
    "type"/Int8ub,
    "length"/Int8ub,
    "cmdargs"/Int8ub,
    "string"/Bytes(this.length-1),
)

def binkp_node_parse(host, port, connect_timeout=10, read_timeout=3):
    start_time = datetime.now().replace(microsecond=0)
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(connect_timeout)
    s.connect((host, port))
    s.settimeout(read_timeout)
    time.sleep(1)
    realdata = bytearray()
    while True:
        data = ''
        try:
            data = s.recv(128)
        except socket.timeout:
            break
        if not data:
            time.sleep(0.1)
            continue
        elif data == '':
            break
        realdata.extend(data)
    s.close()
    stop_time = datetime.now().replace(microsecond=0)
    req_duration = stop_time - start_time
    parser = GreedyRange(binkp10format)
    x = parser.parse(realdata)
    for item in x:
        # TODO: actually check using type most significant bit, etc.
        d_item = item.string.decode('ascii')
        if d_item[0:5] == 'TIME ':
            node_time = d_item.split('TIME ')[1]
            #print("GOT TIME: {}".format(node_time))
            binkpdate = dateparser.parse(node_time)
            print("BINKP DATE: {}".format(binkpdate))
            # TODO:
            today = datetime.now(binkpdate.tzinfo).replace(microsecond=0)
            #pprint(today)
            print("LOCAL DATE: {}".format(today))
            delta = today - binkpdate
            print("DURATION: {}".format(req_duration.seconds))
            pprint(delta.seconds)
            return(delta.seconds-req_duration.seconds)
    # FIX: No TIME ?
    return(None)


class BinkpNodeCheck(nagiosplugin.Resource):
    def __init__(self, host, port, conn_timeout, read_timeout):
        self.host = host
        self.port = port
        self.conn_timeout = conn_timeout
        self.read_timeout = read_timeout

    def probe(self):
        time_diff = binkp_node_parse(self.host, port=self.port, connect_timeout=self.conn_timeout, read_timeout=self.read_timeout)
        print(time_diff)
        if time_diff is None:
            return[nagiosplugin.Metric('binkpnodedrift',-1,context='default')]
        # FIX: use nagiosplugin.state.Unknown in LoadSummary?
        return [nagiosplugin.Metric('binkpnodedrift',
                                    time_diff,
                                    context='default')]


class LoadSummary(nagiosplugin.Summary):
    def __init__(self, domain, port):
        self.domain = domain
        self.port = port
    pass


@nagiosplugin.guarded
def main():
    argp = argparse.ArgumentParser(description=__doc__)
    # FIX: find good values for warning/critical
    argp.add_argument('-w', '--warning', metavar='RANGE', default='6:10',
                      help='warning SECONDS drift. Default=6:10')
    argp.add_argument('-c', '--critical', metavar='RANGE', default='0:5',
                      help='critical SECONDS drift. Default=0:5')
    argp.add_argument('-v', '--verbose', action='count', default=0,
                      help='be more verbose')
    argp.add_argument('-p', '--port', metavar='PORT', default=24554, type=int,
                      help='Remote PORT for binkp service. Default is 24554.')
    argp.add_argument('domain')
    args = argp.parse_args()
    wrange = '@{}'.format(args.warning)
    crange = '@{}'.format(args.critical)
    fmetric = '{value} days until domain expires'
    # FIX: add 'isvaliddomainname' test
    check = nagiosplugin.Check(BinkpNodeCheck(args.domain, args.port, CONN_TIMEOUT, READ_TIMEOUT),
                               nagiosplugin.ScalarContext('daystoexpiration',
                                                          warning=wrange,
                                                          critical=crange,
                                                          fmt_metric=fmetric),
                               LoadSummary(args.domain, args.port))
    check.main(verbose=args.verbose)


if __name__ == '__main__':
    main()
