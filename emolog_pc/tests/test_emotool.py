import asyncio
from io import BytesIO
from socket import socketpair
import sys

import pytest

import emolog
import emotool


async def _emotool_with_sine(runtime=None):
    loop = asyncio.get_event_loop()
    # setup arguments for emotool
    sys.argv = [
        'emotool.py', '--csv', 'tests',
        '--fake-sine', '--elf', 'tests/example.out', '--var', 'xthing,1,0']
    if runtime is not None:
        sys.argv.extend(['--runtime', str(runtime)])
    emotask = loop.create_task(emotool.amain())
    await asyncio.sleep(0.1 if runtime is None else runtime * 3 + 0.1)
    # kill emotask to avoid warning at exit of tests


def test_base():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_emotool_with_sine())


def test_runtime():
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_emotool_with_sine(runtime=0.05))
    raise Exception()
