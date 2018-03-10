import asyncio
from datetime import datetime
import os
from os import listdir, unlink, system, getcwd, chdir
from struct import pack, unpack
from io import BytesIO
from socket import socketpair
import sys
from tempfile import mkdtemp
from shutil import rmtree
from linecache import getlines
from time import time

import pytest

from emolog.emotool.main import (read_elf_variables, EmoToolClient, main)
from emolog.decoders import ArrayDecoder, Decoder
from emolog.cylib import SamplerSample, emo_decode
from emolog.fakeembedded import FakeSineEmbedded


async def _client_test_helper(client, loop):
    await client.send_version()
    await client.send_sampler_stop()
    await client.send_sampler_clear()
    await client.send_set_variables([
        dict(
            name="foo",
            phase_ticks=0,
            period_ticks=1,
            address=123,
            size=4,
            _type=Decoder(b'f', b'l'))])
    await client.send_sampler_start()
    # NOTE: linux passes with 0.01, windows needs more time, 0.1.. why?
    # worthy of checking. How will it affect serial?
    await asyncio.sleep(1.0)


async def _test_client_and_sine_helper(loop, client_end, embedded_end=None, stop_after=None):
    ticks_per_second = 20000
    client_orig = EmoToolClient(
        ticks_per_second=ticks_per_second,
        dump=False, verbose=True, debug=False)
    client_transport, client = await loop.create_connection(lambda: client_orig, sock=client_end)
    if embedded_end is not None:
        embedded_transport, embedded = await loop.create_connection(
            lambda: FakeSineEmbedded(ticks_per_second, stop_after=stop_after),
            sock=embedded_end)
    _client_sine_test = lambda loop: _client_test_helper(client=client, loop=loop)
    return client, _client_sine_test


async def _test_client_and_sine_socket_pair(loop, stop_after=None):
    rsock, wsock = socketpair()
    return await _test_client_and_sine_helper(loop=loop,
                                        client_end=wsock,
                                        embedded_end=rsock,
                                        stop_after=stop_after)


def get_event_loop_with_exception_handler():
    loop = asyncio.get_event_loop()
    def exception_handler(loop, context):
        print(f"caught exception in test: {context}")
        raise Exception(str(context))
    loop.set_exception_handler(exception_handler)
    return loop


def test_client_and_fake_thingy():
    loop = get_event_loop_with_exception_handler()
    client, main = loop.run_until_complete(_test_client_and_sine_socket_pair(loop))
    client.reset('temp.csv', ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'], 1, 100)
    loop.run_until_complete(main(loop))
    assert client.cylib.samples_received == 100


def test_client_restart():
    loop = get_event_loop_with_exception_handler()
    loop.set_debug(True)
    client, main = loop.run_until_complete(_test_client_and_sine_socket_pair(loop, stop_after=10))
    client.reset('temp.csv', ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h'], 1, 50)
    loop.run_until_complete(main(loop))
    assert client.cylib.samples_received >= 50 # assert that client restarted after it detected the pause at 500



def qt_event_loop():
    from PyQt5.QtWidgets import QApplication
    from quamash import QEventLoop
    app = QApplication([])
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    return loop


try:
    import PyQt5
    import quamash
except:
    pass
else:
    if False: # TODO - see above temporarily_disabled_test_client_and_fake_thingy comment
        # TODO - use the skip_if function, don't remember API atm
        def test_client_and_fake_thingy_qt_loop():
            loop = qt_event_loop()
            client, main = loop.run_until_complete(_test_client_and_sine_socket_pair(loop))
            with loop:
                loop.run_until_complete(main(loop))
            assert client.cylib.samples_received > 0



def test_emotool_with_gen():
    getcsv = lambda: {x for x in listdir('.') if x.endswith('.csv')}
    cwd = getcwd()
    start = datetime.utcnow().timestamp() * 1000
    try:
        d = mkdtemp()
        chdir(d)
        original = getcsv()
        with open('local_machine_config.ini', 'w+') as fd:
            fd.write("[folders]\noutput_folder=.\n")
        system('emotool --fake gen --runtime 0.1')
        newfiles = list(sorted(getcsv() - original))
        contents = [getlines(f) for f in newfiles]
    finally:
        chdir(cwd)
        rmtree(d)
    assert len(newfiles) == 1
    assert len(contents) == 1
    lines = contents[0]
    assert len(lines) >= 2
    assert lines[0].count(',') == lines[1].count(',')
    res_t = float(lines[1].split(',')[2])
    assert abs(res_t - start) < 1000


def test_read_elf_variables():
    read_elf_variables(os.path.join('tests', 'example.out'), ['var_int,1,0', 'var_float,1,0', 'var_unsigned_char,1,0', 'var_float8,1,0'], None)


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


def test_args():
    try:
        main(['--fake', 'gen', '--runtime', '0.0001', '--help'])
    except SystemExit:
        pass # good


if __name__ == '__main__':
    test_client_and_fake_thingy()
