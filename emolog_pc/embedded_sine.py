#!/bin/env python

from asyncio import get_event_loop

from fcntl import fcntl, F_GETFL, F_SETFL
from sys import stdin
from os import O_NONBLOCK

from emolog.lib import FakeSineEmbedded, AsyncIOEventLoop, TransportStdinAndOut


def set_nonblocking(fd):
    orig_fl = fcntl(fd, F_GETFL)
    fcntl(fd, F_SETFL, orig_fl | O_NONBLOCK)

def main():
    set_nonblocking(stdin)
    loop = get_event_loop()
    loop.set_debug(True)
    embedded = FakeSineEmbedded(AsyncIOEventLoop(loop), transport=TransportStdinAndOut())
    loop.run_forever()

if __name__ == '__main__':
    main()
