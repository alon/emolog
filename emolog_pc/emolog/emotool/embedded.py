#!/bin/env python3

"""
Create an emolog speaking embedded client for testing purposes
"""

from argparse import ArgumentParser
import sys
import asyncio

from .. import dwarfutil
from ..fakeembedded import FakeSineEmbedded



def main():
    parser = ArgumentParser()
    parser.add_argument('--ticks-per-second', type=float, required=True)
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--build-timestamp-value', type=int, required=True)
    parser.add_argument('--embedded', action='store_true', required=True) # see the way this is called from emotool
    args, _ = parser.parse_known_args(sys.argv[1:])
    ticks_per_second = args.ticks_per_second
    port = args.port
    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        loop.create_server(
            lambda: FakeSineEmbedded(ticks_per_second=ticks_per_second,
                                     build_timestamp_value=args.build_timestamp_value,
                                     build_timestamp_addr=dwarfutil.FakeElf.build_timestamp_address),
            host='127.0.0.1', port=port))
    while True:
        try:
            loop.run_forever()
        except KeyboardInterrupt:
            continue
        except:
            raise


if __name__ == '__main__':
    main()
