#!/usr/bin/env python3

import ctypes
import struct
import argparse
import sys

from serial import Serial
from serial.tools.list_ports import comports

from emolog.lib import encode_version, ClientParser, Version, SkipBytes, get_seq


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--serial', default=None, help='serial port to connect to (platform specific)')
    args = parser.parse_args()
    serial = emolog.get_serial(comport=args.serial, hint_description='stellaris')
    print("library seq: {}".format(get_seq()))
    print("opening port {}".format(args.serial))
    serial = Serial(args.serial, baudrate=115200)
    parser = ClientParser(serial=serial)
    def version_and_parse():
        msg = parser.send_command(encode_version())
        if isinstance(msg, Version):
            print("got version message from client. version = {}".format(msg.version))
        elif isinstance(msg, SkipBytes):
            print("parser state: {}".format(parser))
            raise SystemExit
    version_and_parse()
    version_and_parse()


if __name__ == '__main__':
    main()
