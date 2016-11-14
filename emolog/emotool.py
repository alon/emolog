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


def dwarf_get_variables_by_name(filename, names, verbose):
    file_parser = FileParser(filename=filename)
    sampled_vars = {}
    found = set()
    elf_vars = list(file_parser.visit_interesting_vars_tree_leafs())
    elf_var_names = [v.get_full_name() for v in elf_vars]
    lower_to_actual = {name.lower(): name for name in elf_var_names}
    elf_var_names_set_lower = set(lower_to_actual.keys())
    for v in elf_vars:
        v_name = v.get_full_name()
        if verbose:
            print("candidate {}".format(v_name))
        if v_name in names:
            sampled_vars[v_name] = v
            found.add(v_name)
    given = set(names)
    if given != found:
        print("Error: the following variables were not found in the ELF:\n{}".format(", ".join(list(given - found))))
        elf_name_to_options = {name: set(with_errors(name)) for name in elf_var_names_set_lower}
        missing_lower = [name.lower() for name in given - found]
        missing_lower_to_actual = {name.lower(): name for name in given - found}
        missing_to_errors = {name: set(with_errors(name)) for name in missing_lower}
        for name in missing_lower:
            options = [elf_name for elf_name, elf_options in elf_name_to_options.items() if len(missing_to_errors[name] & elf_options) > 0]
            if len(options) > 0:
                print("{} is close to {}".format(missing_lower_to_actual[name], ", ".join(lower_to_actual[x] for x in options)))
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
    def __init__(self, csv, fd, verbose, names):
        super(EmoToolClient, self).__init__(verbose=verbose)
        self.csv = csv
        self.fd = fd
        self.csv.writerow(['sequence', 'ticks', 'timestamp'] + names)

    def handle_sampler_sample(self, msg):
        # todo - decode variables (integer/float) in emolog VariableSampler
        self.csv.writerow([msg.seq, msg.ticks, time.clock() * 1000] + msg.variables)
        self.fd.flush()


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


def decode_little_endian_float(s):
    return struct.unpack('<f', s)[0]


def str_size_to_decoder(s, size):
    if s.endswith('float'):
        if size == 4:
            return decode_little_endian_float
    else: # might be broken since s which is dwarf.dwarf.VarDescriptor.get_type_name() doesn't necessarily end with 'int' / 'float'
        # Note: will support both int and enum
        if size == 4:
            return lambda q: struct.unpack('<l', q)[0]
        elif size == 2:
            return lambda q: struct.unpack('<h', q)[0]
        elif size == 1:
            return ord
    print("type names supported: int, float. looked for: {}, {}".format(s, size))
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
    parser.add_argument('--var', default=[], action='append', help='add a single var, example "foo,float,1,0" = "varname,vartype,ticks,tickphase"')
    parser.add_argument('--varfile', help='file containing variable definitions, identical to multiple --var calls')
    parser.add_argument('--csv-filename', default=None, help='name of csv output file')
    parser.add_argument('--verbose', default=False, action='store_true', help='turn on verbose logging')
    parser.add_argument('--runtime', type=float, help='quit after given seconds')
    parser.add_argument('--baud', default=1000000, help='baudrate, using RS422 up to 12000000 theoretically', type=int)
    args = parser.parse_args()
    if args.varfile is not None:
        with open(args.varfile) as fd:
            args.var = args.var + fd.readlines()
    split_vars = [[x.strip() for x in v.split(',')] for v in args.var]
    for v, orig in zip(split_vars, args.var):
        if len(v) != 3 or not an_int(v[1]) or not an_int(v[2]):
            print("problem with '--var' argument {!r}".format(orig))
            print("--var parameter must be a 4 element comma separated list of: <name>,<period:int>,<phase:int>")
            raise SystemExit
    names = [name for name, ticks, phase in split_vars]
    name_to_ticks_and_phase = {name: (int(ticks), int(phase)) for name, ticks, phase in split_vars}
    dwarf_variables = dwarf_get_variables_by_name(args.elf, list(name_to_ticks_and_phase.keys()), verbose=args.verbose)
    if len(dwarf_variables) == 0:
        print("error - no variables set for sampling")
        raise SystemExit
    variables = []
    for name in names:
        v = dwarf_variables[name]
        period_ticks, phase_ticks = name_to_ticks_and_phase[name]
        variables.append(dict(phase_ticks=phase_ticks, period_ticks=period_ticks,
                              address=v.address, size=v.size,
                              _type=str_size_to_decoder(v.get_type_str(), v.size)))

    csv_filename = (next_available('emo', numbered=True) if not args.csv_filename else
                    next_available(args.csv_filename, numbered=False))
    print("================")
    print("Emotool starting")
    print("================")
    print("")
    print("creating output {}".format(csv_filename))
    csv_fd = open(csv_filename, 'w+')
    csv_obj = csv.writer(csv_fd, lineterminator='\n')
    loop = asyncio.get_event_loop()
    if args.runtime:
        async def quit_after_runtime():
            await asyncio.sleep(args.runtime)
            raise SystemExit
        loop.create_task(quit_after_runtime())
    client = EmoToolClient(csv=csv_obj, fd=csv_fd, verbose=args.verbose, names=names)
    if args.fake_sine:
        client_end = await start_fake_sine()
        client_transport, client = await loop.create_connection(lambda: client, sock=client_end)
    else:
        client = await emolog.get_serial_client(comport=args.serial, hint_description=args.serial_hint,
                                                baudrate=args.baud,
                                                protocol=lambda: client)
    await client.send_version()
    await client.send_sampler_stop()
    await client.send_set_variables(variables)
    await client.send_sampler_start()
    return client


def windows_try_getch():
    import msvcrt
    if msvcrt.kbhit():
        return msvcrt.getch()
    return None # be explicit


if sys.platform == 'win32':
    try_getch_message = 'Press any key to exit'
    try_getch = windows_try_getch
else:
    try_getch_message = "Press Ctrl-C to exit"
    def try_getch():
        return None


async def amain_with_loop():
    client = await amain()
    print(try_getch_message)
    try:
        while True:
            if try_getch():
                break
            await asyncio.sleep(0.1)
    except KeyboardInterrupt:
        pass
    print("sending sampler stop")
    await client.send_sampler_stop()


def main():
    if sys.platform == 'win32':
        asyncio.set_event_loop(asyncio.ProactorEventLoop())

    asyncio.get_event_loop().run_until_complete(amain_with_loop())


if __name__ == '__main__':
    main()
