#!/usr/bin/env python3

import ctypes
import struct
import argparse
import sys

from serial import Serial
from serial.tools.list_ports import comports

from emolog import ClientParser, Version, get_seq, HostSampler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--serial', default=None, help='serial port to connect to (platform specific)')
    parser.add_argument('--filename', required=True, help='DWARF file to read variables from')
    args = parser.parse_args()
    if args.serial is None:
        stellaris = [x for x in comports() if 'stellaris' in x.description.lower()]
        if len(stellaris) == 0:
            print("no stellaris com port found - is the board connected and powered?")
            raise SystemExit
        if len(stellaris) > 1:
            print("picking the first out of available {}".format(','.join([x.device for x in stellaris])))
        args.serial = stellaris[0].device
    print("library seq: {}".format(get_seq()))
    print("opening port {}".format(args.serial))
    serial = Serial(args.serial, baudrate=115200)

    parser = ClientParser(serial)

    # initialize sampler
    sampler = HostSampler(parser)
    sampler.stop()
    # clear buffer from any commands the client may have sent us
    serial.flushInput()

    msg = parser.send_command(Version())
    if isinstance(msg, Version):
        print("got version message from embedded. version = {}".format(msg.version))
    else:
        print("unexpected message from embedded: {}".format(repr(msg)))

    file_parser = FileParser(filename=args.filename)
    for v in file_parser.visit_interesting_vars_tree_leafs():
        sampler.set_variables([dict(phase_ticks=0, period_ticks=200000, address=v.address, size=v.size)])
    for msg in sampler.read_samples():
        print(repr(msg))


if __name__ == '__main__':
    main()
