import asyncio
import os
from struct import pack, unpack
from io import BytesIO
from socket import socketpair
import sys

import pytest

from emolog.emotool.main import (read_elf_variables)
from emolog.decoders import ArrayDecoder
from emolog.cylib import SamplerSample, emo_decode

#
# async def _emotool_with_sine(runtime=None):
#     loop = asyncio.get_event_loop()
#     # setup arguments for emotool
#     sys.argv = [
#         'emotool', '--fake', '--elf', 'tests/example.out', '--var', 'xthing,1,0']
#     if runtime is not None:
#         sys.argv.extend(['--runtime', str(runtime)])
#     emotask = loop.create_task(emotool.amain())
#     await asyncio.sleep(0.1 if runtime is None else runtime * 3 + 0.1)
#     # kill emotask to avoid warning at exit of tests


# def test_base():
#     loop = asyncio.get_event_loop()
#     loop.run_until_complete(_emotool_with_sine())


# def test_runtime():
#     loop = asyncio.get_event_loop()
#     loop.run_until_complete(_emotool_with_sine(runtime=0.05))
#     raise Exception()

# def test_read_elf_variables():
#     read_elf_variables(os.path.join('tests', 'example.out'), ['var_int,1,0', 'var_float,1,0', 'var_unsigned_char,1,0', 'var_float8,1,0'], None)


def test_array_decoder():
    assert '{ 1, 2, 3 }' == ArrayDecoder(b'foo', b'i', 3).decode(pack('<3i', 1, 2, 3))
    assert '{ 1.000, 2.000, 3.000 }' == ArrayDecoder(b'bar', b'f', 3).decode(pack('<3f', 1.0, 2.0, 3.0))

# Timing functions - for use with ipython:
# %timeit blabla


def setup_emo_decode_sample():
    sample = bytes(SamplerSample(seq=1, ticks=2, var_size_pairs=[(4,4),(8,4)]).encode())
    return sample


def time_emo_decode_sample(sample):
    return emo_decode(sample, 0)
