import asyncio
from io import BytesIO
from socket import socketpair

import pytest

import emolog


test_decode_sanity_data = [
    ('version', emolog.Version, {}),
    ('ping', emolog.Ping, {}),
    ('ack', emolog.Ack, {"reply_to_seq": 5, "error": 0}),
    ('sampler_register_variable', emolog.SamplerRegisterVariable,
     {
        'phase_ticks': 1,
        'period_ticks': 2,
        'address': 128,
        'size': 4
     }),
    ('sampler_clear', emolog.SamplerClear, {}),
    ('sampler_start', emolog.SamplerStart, {}),
    ('sampler_stop', emolog.SamplerStop, {}),
    ('sampler_sample', emolog.SamplerSample,
     {
         "ticks": 256,
         "var_size_pairs": [(512, 2), (1024, 4)]
     }),
]


@pytest.mark.parametrize("name,reply_class,params", test_decode_sanity_data)
def test_decode_sane(name, reply_class, params):
    encoded = reply_class(seq=0, **params).encode()
    msg, remaining_buf = emolog.emo_decode(encoded)
    assert isinstance(msg, reply_class), "expected {}, got {}".format(reply_class, str(msg))
    assert len(remaining_buf) == 0


def test_client_parser():
    serial = BytesIO()
    parser = emolog.Parser(serial)


def test_client_with_c_thing():
    # TODO
    pass


def _client_test_helper(client, loop):
    client.send_version()
    client.send_sampler_stop()
    client.send_sampler_clear()
    client.send_set_variables([dict(phase_ticks=0, period_ticks=2, address=123, size=4)])
    client.send_sampler_start()
    # NOTE: linux passes with 0.01, windows needs more time, 0.1.. why?
    # worthy of checking. How will it affect serial?
    yield from asyncio.sleep(0.1)
    loop.stop()


def _test_client_and_sine_helper(eventloop, client_end, embedded_end=None):
    client = emolog.Client(eventloop=eventloop, transport=client_end)
    if embedded_end is not None:
        embedded = emolog.FakeSineEmbedded(eventloop=eventloop, transport=embedded_end)
    _client_sine_test = lambda loop: _client_test_helper(client=client, loop=loop)
    return client, _client_sine_test


def _test_client_and_sine_socket_pair(eventloop):
    rsock, wsock = socketpair()
    return _test_client_and_sine_helper(eventloop=eventloop,
                                        client_end=emolog.SocketToFile(wsock),
                                        embedded_end=emolog.SocketToFile(rsock))


def test_client_and_fake_thingy():
    loop = asyncio.get_event_loop()
    eventloop = emolog.AsyncIOEventLoop(loop)
    client, main = _test_client_and_sine_socket_pair(eventloop)
    loop.run_until_complete(main(loop))
    assert client.received_samples > 0


def qt_event_loop():
    from PyQt5.QtWidgets import QApplication
    from quamash import QEventLoop
    app = QApplication([])
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    return loop


try:
    import PyQt5
except:
    pass
else:
    # TODO - use the skip_if function, don't remember API atm
    def test_client_and_fake_thingy_qt_loop():
        loop = qt_event_loop()
        eventloop = emolog.AsyncIOEventLoop(loop)
        client, main = _test_client_and_sine_socket_pair(eventloop)
        with loop:
            loop.run_until_complete(main(loop))
        assert client.received_samples > 0


def failed_blasted_data_not_reaching_subprocess_test_client_and_fake_thingy_qt_pipe():
    """
    This is as close to the gui as possible - uses a pipe that is akin to
    using a tty/COM device, i.e. serial USB connection to the TI, as
    with the real hardware
    """
    eventloop = qt_event_loop()
    eventloop.set_debug(True)
    def main():
        client_to_fake = emolog.ClientToFake(eventloop=eventloop)
        yield from client_to_fake.initialize()
        yield from _client_test_helper(client=client_to_fake.client, loop=eventloop)
    with eventloop:
        eventloop.run_until_complete(main())

