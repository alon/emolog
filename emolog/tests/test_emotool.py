import asyncio
from io import BytesIO
from socket import socketpair
import sys

import pytest

import emolog
import emotool


async def _emotool_with_sine():
    loop = asyncio.get_event_loop()
    # setup arguments for emotool
    sys.argv = ['emotool.py', '--fake-sine', '--elf', 'tests/example.out', '--var', 'xthing,int,1,0']
    emotask = loop.create_task(emotool.amain())
    await asyncio.sleep(0.1)
    # kill emotask to avoid warning at exit of tests



def test_base():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_emotool_with_sine())

