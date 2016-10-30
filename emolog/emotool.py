#!/bin/env python

import time
import sys
import os
import csv
import struct
import asyncio
import argparse
from socket import socketpair

from dwarf import FileParser
import emolog


def getvars(filename, varparts, verbose):
    file_parser = FileParser(filename=filename)
    print("varparts = {}".format(varparts))
    sampled_vars = []
    for v in file_parser.visit_interesting_vars_tree_leafs():
        if verbose:
            print("candidate {}".format(v.name))
        if v.name in varparts:
            sampled_vars.append(v)
    print("Registering variables from {}".format(filename))
    for v in sampled_vars:
        print("   {}".format(v.get_full_name()))
    return sampled_vars


async def start_fake_sine():
    loop = asyncio.get_event_loop()
    rsock, wsock = socketpair()
    await loop.create_connection(emolog.FakeSineEmbedded, sock=rsock)
    return wsock


def unpack(x):
    if len(x) == 4:
        return struct.unpack('<i', x)[0]
    elif len(x) == 2:
        return struct.unpack('<h', x)[0]
    elif len(x) == 1:
        return ord(x)
    return 0


class EmoToolClient(emolog.Client):
    def __init__(self, csv, verbose):
        super(EmoToolClient, self).__init__(verbose=verbose)
        self.csv = csv

    def handle_sampler_sample(self, msg):
        # todo - decode variables (integer/float) in emolog VariableSampler
        self.csv.writerow([time.time()] + [unpack(x) for x in msg.variables])


def iterate(filename, initial, firstoption):
    if firstoption is not None:
        if firstoption[-4:] != '.csv':
            yield '{}.csv'.format(firstoption)
        else:
            yield firstoption
    if filename[-4:] == '.csv':
        filename = filename[:-4]
    while True:
        yield '{}_{:03}.csv'.format(filename, initial)
        initial += 1


def next_available(filename, numbered):
    filenames = iterate(filename, 1, filename if numbered is None else None)
    for filename in filenames:
        if not os.path.exists(filename):
            return filename


async def amain():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fake-sine', default=False, action='store_true', help='debug only - use a fake sine producing client')
    parser.add_argument('--serial', default=None, help='serial port to use')
    parser.add_argument('--serial-hint', default='stellaris', help='usb description for serial port to filter on')
    parser.add_argument('--elf', default=None, required=True, help='elf executable running on embedded side')
    parser.add_argument('--var-parts', default='sawtooth,sine', help='all vars including one of the strings will be shown')
    parser.add_argument('--rate', type=int, default=1000, help='number of ticks to wait between samples')
    parser.add_argument('--csv-filename', default=None, help='name of csv output file')
    parser.add_argument('--verbose', default=False, action='store_true', help='turn on verbose logging')
    args = parser.parse_args()
    sampled_vars = getvars(args.elf, args.var_parts.split(','), verbose=args.verbose)
    var_dict = [dict(phase_ticks=0, period_ticks=args.rate, address=v.address, size=v.size) for v in sampled_vars]
    if len(var_dict) == 0:
        print("error - no variables set for sampling")
        raise SystemExit

    csv_filename = (next_available('emo', numbered=True) if not args.csv_filename else
                    next_available(csv_filename, numbered=False))
    csv_obj = csv.writer(open(csv_filename, 'w+'))
    client = EmoToolClient(csv=csv_obj, verbose=args.verbose)
    if args.fake_sine:
        loop = asyncio.get_event_loop()
        client_end = await start_fake_sine()
        client_transport, client = await loop.create_connection(lambda: client, sock=client_end)
    else:
        client = await emolog.get_serial_client(comport=args.serial, hint_description=args.serial_hint,
                                                protocol=lambda: client)
    await client.send_version()
    await client.send_sampler_stop()
    await client.send_set_variables(var_dict)
    await client.send_sampler_start()


async def amain_with_loop():
    await amain()
    # TODO? ctrl-c
    loop = asyncio.get_event_loop()
    f = loop.create_future()
    await f # just a way to wait indefinitely


def main():
    if sys.platform == 'win32':
        asyncio.set_event_loop(asyncio.ProactorEventLoop())

    asyncio.get_event_loop().run_until_complete(amain_with_loop())


if __name__ == '__main__':
    main()
