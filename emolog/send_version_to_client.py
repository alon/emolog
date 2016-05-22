#!/usr/bin/env python3

import ctypes
import struct
import argparse
import sys

from serial import Serial
from serial.tools.list_ports import comports

from emolog import write_version, ClientParser, Version, SkipBytes, get_seq


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
    s = Serial(args.serial, baudrate=115200)
    success = 0
    write_version(s)
    parser = ClientParser()
    while success < 2:
        msg = parser.incoming(s.read())
        if isinstance(msg, Version):
            print("got version message from client. version = {}".format(msg.version))
            success += 1
            if success < 2:
                write_version(s)
        elif isinstance(msg, SkipBytes):
            print("parser state: {}".format(parser))
            raise SystemExit



if __name__ == '__main__':
    main()
