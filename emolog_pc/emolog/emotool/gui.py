#!/usr/bin/env python3

from datetime import datetime
import os
import ctypes
import struct
import argparse
import sys

import qt5

from serial import Serial
from serial.tools.list_ports import comports

from dwarf import FileParser
from emolog.lib import ClientParser, Version, get_seq, HostSampler


class BiDiPipe(object):
    verbose = True

    def __init__(self, pipeout, pipein):
        self.outp = open(pipeout, 'wb')
        self.inp = open(pipein, 'rb')

    def _verbose(self, s):
        if not self.verbose:
            return
        print('Pipe: {}'.format(s))

    def write(self, s):
        self._verbose(repr(s))
        self.outp.write(s)
        self.outp.flush()

    def read(self):
        read = self.inp.read()
        if len(read) == 0:
            raise EOFError('read end closed')
        self._verbose(repr(read))
        return read

    def flushInput(self):
        self.inp.flush()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--serial', default=None, help='serial port to connect to (platform specific)')
    parser.add_argument('--filename', required=True, help='DWARF file to read variables from')
    parser.add_argument('--pipe', required=False, help="comma separated pair of fifo names for testing")
    args = parser.parse_args()
    if args.serial is None and args.pipe is None:
        stellaris = [x for x in comports() if 'stellaris' in x.description.lower()]
        if len(stellaris) == 0:
            print("no stellaris com port found - is the board connected and powered?")
            raise SystemExit
        if len(stellaris) > 1:
            print("picking the first out of available {}".format(','.join([x.device for x in stellaris])))
        args.serial = stellaris[0].device

    if args.pipe is not None and args.serial is not None:
        print("error: cannot use serial and pipe at the same time")
        raise SystemExit

    print("parsing TI out file {}".format(args.filename))
    file_parser = FileParser(filename=args.filename)
    for v in file_parser.visit_interesting_vars_tree_leafs():
        print("   {}".format(v.get_full_name()))

    print("library seq: {}".format(get_seq()))
    print("opening port {}".format(args.serial or args.pipe))

    def generate_samples():
        if args.pipe:
            pipes = args.pipe.split(',')
            assert len(pipes) == 2 and os.path.exists(pipes[0]) and os.path.exists(pipes[1])
            comm = BiDiPipe(pipeout=pipes[0], pipein=pipes[1])
        else:
            comm = Serial(args.serial, baudrate=115200)

        parser = ClientParser(comm)

        # initialize sampler
        sampler = HostSampler(parser)
        sampler.stop()
        # clear buffer from any commands the client may have sent us
        comm.flushInput()

        msg = parser.send_command(Version())
        if isinstance(msg, Version):
            print("got version message from embedded. version = {}".format(msg.version))
        else:
            print("unexpected message from embedded: {}".format(repr(msg)))

        sampled_vars = [v for v in file_parser.visit_interesting_vars_tree_leafs() if v.name in ['sawtooth', 'sine']] # TEMP test only
        var_dict = [dict(phase_ticks=0, period_ticks=1, address=v.address, size=v.size) for v in sampled_vars]
        print("sampling:")
        for v in sampled_vars:
            print("{:20}: address 0x{:10}, size {:4}".format(v.name, hex(v.address), v.size))
        sampler.set_variables(var_dict)
        yield sampled_vars
        for msg in sampler.read_samples():
            yield msg

    t = []
    gen = generate_samples()
    sampled_vars = gen.send(None)
    vars = [[] for i in range(len(sampled_vars))]
    qt5.callback = lambda: [struct.unpack('<'+t, x)[0] for t, x in zip('lf', gen.send(None).variables)]
    qt5.main()
    start = last = datetime.now()
    for new_raw_vals in gen:
        cur = datetime.now()
        raw_int, raw_float = new_raw_vals.variables
        new_vals = struct.unpack('<lf', raw_int + raw_float)
        print('{} (+{}): {}'.format(cur - start, cur - last, new_vals))
        last = cur


if __name__ == '__main__':
    main()
