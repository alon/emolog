#!/usr/bin/env python3

import ctypes
import struct

from serial import Serial

from emolog import write_version, ClientParser, Version, SkipBytes, get_seq


def main():
    print("library seq: {}".format(get_seq()))
    s = Serial('/dev/ttyACM0', baudrate=115200)
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
