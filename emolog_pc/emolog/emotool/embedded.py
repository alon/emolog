#!/bin/env python

"""
Create an emolog speaking embedded client for testing purposes
"""

import sys
import asyncio

from ..fakeembedded import FakeSineEmbedded


def main():
    ticks_per_second = float(sys.argv[-2])
    port = int(sys.argv[-1])
    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        loop.create_server(
            lambda: FakeSineEmbedded(ticks_per_second),
            host='127.0.0.1', port=port))
    loop.run_forever()

if __name__ == '__main__':
    main()
