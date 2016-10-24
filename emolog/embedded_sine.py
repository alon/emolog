#!/bin/env python

import asyncio

import fcntl
import sys
import os

import emolog


def set_nonblocking(fd):
    orig_fl = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, orig_fl | os.O_NONBLOCK)

def main():
    set_nonblocking(sys.stdin)
    loop = asyncio.get_event_loop()
    loop.set_debug(True)
    embedded = emolog.FakeSineEmbedded(emolog.AsyncIOEventLoop(loop),
                                       transport=emolog.TransportStdinAndOut())
    loop.run_forever()

if __name__ == '__main__':
    main()
