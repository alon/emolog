#!/bin/env python

import time
import sys
import os
import csv
import struct
import asyncio
import argparse
import string
from socket import socketpair

from dwarf import FileParser
import emolog


def with_errors(s):
    # TODO - find a library for this? using error distance
    yield s
    #  deleted element
    for i in range(0, len(s)):
        yield s[:i] + s[i + 1:]
    # rotated adjacent elements
    for i in range(0, len(s) - 1):
        yield s[:i] + s[i + 1] + s[i] + s[i + 2:]
    if len(s) > 3:
        # 26**3 is already ~ 1e5 is too much
        return
    # single complete alphabet typing errors - this is really large..
    for i in range(0, len(s)):
        for other in string.ascii_lowercase:
            yield s[:i] + other + s[i + 1:]


def getvars(filename, names, verbose):
    file_parser = FileParser(filename=filename)
    sampled_vars = {}
    found = set()
    elf_vars = list(file_parser.visit_interesting_vars_tree_leafs())
    elf_var_names = [v.name for v in elf_vars]
    lower_to_actual = {name.lower(): name for name in elf_var_names}
    elf_var_names_set_lower = set(lower_to_actual.keys())
    for v in elf_vars:
        if verbose:
            print("candidate {}".format(v.name))
        if v.name in names:
            sampled_vars[v.name] = v
            found.add(v.name)
    given = set(names)
    if given != found:
        print("Error: the following variables were not found in the ELF:\n{}".format(", ".join(list(given - found))))
        elf_name_to_options = {name: set(with_errors(name)) for name in elf_var_names}
        missing = {name: set(with_errors(name)) for name in given - found}
        for name in given - found:
            options = [elf_name for elf_name, elf_options in elf_name_to_options.items() if len(missing[name] & elf_options) > 0]
            if len(options) > 0:
                print("{} is close to {}".format(name, ", ".join(options)))
        raise SystemExit
    print("Registering variables from {}".format(filename))
    for v in sampled_vars.values():
        print("   {}".format(v.get_full_name()))
    return sampled_vars


async def start_fake_sine():
    loop = asyncio.get_event_loop()
    rsock, wsock = socketpair()
    await loop.create_connection(emolog.FakeSineEmbedded, sock=rsock)
    return wsock


class EmoToolClient(emolog.Client):
    def __init__(self, csv, verbose):
        super(EmoToolClient, self).__init__(verbose=verbose)
        self.csv = csv

    def handle_sampler_sample(self, msg):
        # todo - decode variables (integer/float) in emolog VariableSampler
        self.csv.writerow([time.time()] + msg.variables)


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


def str_size_to_decoder(s, size):
    if s == 'int':
        if size == 4:
            return lambda q: struct.unpack('<l', q)[0]
        elif size == 2:
            return lambda q: struct.unpack('<h', q)[0]
        elif size == 1:
            return ord
    elif s == 'float':
        if size == 4:
            return lambda q: struct.unpack('<f', q)[0]
    print("type names supported: int, float")
    raise SystemExit


def an_int(x):
    try:
        b = int(x)
    except:
        return False
    return True


async def amain():
    parser = argparse.ArgumentParser(description='Emolog protocol capture tool. Implements emolog client side, captures a given set of variables to a csv file')
    parser.add_argument('--fake-sine', default=False, action='store_true', help='debug only - use a fake sine producing client')
    parser.add_argument('--serial', default=None, help='serial port to use')
    parser.add_argument('--serial-hint', default='stellaris', help='usb description for serial port to filter on')
    parser.add_argument('--elf', default=None, required=True, help='elf executable running on embedded side')
    parser.add_argument('--var', action='append', help='add a single var, example "foo,float,1,0" = "varname,vartype,ticks,tickphase"')
    parser.add_argument('--csv-filename', default=None, help='name of csv output file')
    parser.add_argument('--verbose', default=False, action='store_true', help='turn on verbose logging')
    args = parser.parse_args()
    split_vars = [[x.strip() for x in v.split(',')] for v in args.var]
    for v, orig in zip(split_vars, args.var):
        if len(v) != 4 or not an_int(v[2]) or not an_int(v[3]) or not v[1] in ['int', 'float']:
            print("problem with '--var' argument {!r}".format(orig))
            print("--var parameter must be a 4 element comma separated list of: <name>,[float|int],<period:int>,<phase:int>")
            raise SystemExit
    variables = {name: (lambda size: str_size_to_decoder(_type, size), int(ticks), int(phase)) for name, _type, ticks, phase in split_vars}
    sampled_vars = getvars(args.elf, list(variables.keys()), verbose=args.verbose)
    var_dict = [dict(phase_ticks=variables[name][2], period_ticks=variables[name][1],
                     address=v.address, size=v.size, _type=variables[name][0](v.size)) for name, v in sampled_vars.items()]
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
