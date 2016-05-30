#!/usr/bin/env python3

import ctypes
import struct
import argparse
import sys

from serial import Serial
from serial.tools.list_ports import comports

from emolog import encode_version, ClientParser, Version, get_seq, HostSampler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--serial', default=None, help='serial port to connect to (platform specific)')
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
    msg = parser.send_command(encode_version())
    if isinstance(msg, Version):
        print("got version message from embedded. version = {}".format(msg.version))
    else:
        print("unexpected message from embedded: {}".format(repr(msg)))
    # initialize sampler
    sampler = HostSampler(parser)

    # phase_ticks, period_ticks, address, size
    sampler.set_variables([(0, 1000, 0x100, 4)])
    for msg in sampler.read_samples():
        print(repr(msg))


if __name__ == '__main__':
    main()
