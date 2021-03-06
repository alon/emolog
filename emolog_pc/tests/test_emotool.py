import asyncio
from pathlib import Path
from datetime import datetime
import csv
from os import listdir, system, getcwd, chdir, path
from struct import pack
from socket import socketpair
from tempfile import TemporaryDirectory
from linecache import getlines
from contextlib import contextmanager
from subprocess import check_output


from emolog.consts import BUILD_TIMESTAMP_VARNAME
from emolog.emotool.main import (read_elf_variables, EmoToolClient, main)
from emolog.decoders import ArrayDecoder, Decoder
from emolog.cylib import SamplerSample, emo_decode
from emolog.fakeembedded import FakeSineEmbedded


module_path = path.dirname(__file__)


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
            lambda: FakeSineEmbedded(ticks_per_second, stop_after=stop_after, build_timestamp_addr=74747, build_timestamp_value=91929),
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
        print("caught exception in test: {context}".format(context=context))
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


@contextmanager
def TemporaryDirectoryWithChdir():
    cwd = getcwd()
    with TemporaryDirectory() as d:
        chdir(d)
        try:
            yield d
        finally:
            chdir(cwd)



def test_emotool_with_gen():
    getcsv = lambda: {x for x in listdir('.') if x.endswith('.csv')}
    start = datetime.now().timestamp() * 1000
    for check_timestamp, same_timestamp in [(False, False), (True, False), (True, True)]:
        with TemporaryDirectoryWithChdir() as d:
            original = getcsv()
            with open('local_machine_config.ini', 'w+') as fd:
                fd.write("[folders]\noutput_folder=.\n")
            if same_timestamp:
                elf_timestamp = gen_timestamp = 7572
            else:
                elf_timestamp, gen_timestamp = 8822, 2288
            system('emotool --fake gen --runtime 0.1' +
                   (' --check-timestamp --fake-elf-build-timestamp-value {elf_timestamp} --fake-gen-build-timestamp-value {gen_timestamp}'.format(
                        elf_timestamp=elf_timestamp, gen_timestamp=gen_timestamp) if check_timestamp else ''))
            newfiles = list(sorted(getcsv() - original))
            contents = [getlines(f) for f in newfiles]
            expect_params_file = check_timestamp
            expect_vars_file = not check_timestamp or (check_timestamp and same_timestamp)
            expected_file_count = expect_vars_file + expect_params_file
            assert len(newfiles) == expected_file_count
            assert len(contents) == expected_file_count
            if expect_vars_file:
                ind = [i for i, x in enumerate(newfiles) if 'params' not in x][0]
                lines = contents[ind]
                assert len(lines) >= 2
                assert lines[0].count(',') == lines[1].count(',')
                res_t = float(lines[1].split(',')[2])
                assert abs(res_t - start) < 1500
            if check_timestamp:
                ind = [i for i, x in enumerate(newfiles) if 'params' in x][0]
                assert len(contents[ind]) == 2
                d = dict(zip(*csv.reader(contents[ind])))
                assert BUILD_TIMESTAMP_VARNAME in d
                val = int(d[BUILD_TIMESTAMP_VARNAME])
                assert (same_timestamp and val == elf_timestamp) or val != elf_timestamp


example_out = Path(__file__).parent / 'example.out'
assert (example_out.exists(),
        f"programming error: expected example.out to be in directory of test, {str(example_out.resolve())}")


def test_read_elf_variables():
    names, vars = read_elf_variables(path.join(module_path, str(example_out)), [('var_int', 1, 0), ('var_float',1,0), ('var_unsigned_char',1,0), ('var_float8',1,0)], None)
    d = {k['name']: k['address'] for k in vars}
    got_address = d['var_unsigned_char']
    expected_address = int([x for x in check_output(f'objdump -x {str(example_out)}'.split()).decode().split('\n') if 'var_unsigned_char' in x][0].split()[0], 16)
    assert expected_address == got_address
    breakpoint()


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
