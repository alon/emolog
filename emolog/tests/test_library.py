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


class SocketToFile(object):
    def __init__(self, socket):
        self.socket = socket
        socket.setblocking(False)

    def read(self, n=None):
        if n is None:
            n = 1024
        try:
            return self.socket.recv(n)
        except BlockingIOError:
            return b''

    def write(self, s):
        return self.socket.send(s)


class AsyncIOEventLoop(object):
    def __init__(self, loop):
        self.loop = loop

    def add_reader(self, fdlike, callback):
        if isinstance(fdlike, SocketToFile):
            fd = fdlike.socket
        else:
            fd = fdlike
        self.loop.add_reader(fd, callback)

    def call_later(self, dt, callback):
        self.loop.call_later(dt, callback)


def test_client_and_fake_thingy():
    asyncioloop = asyncio.get_event_loop()
    eventloop = AsyncIOEventLoop(asyncioloop)
    rsock, wsock = socketpair()
    client = emolog.Client(eventloop=eventloop, transport=SocketToFile(wsock))
    embedded = emolog.FakeSineEmbedded(eventloop=eventloop, transport=SocketToFile(rsock))
    def test():
        client.send_version()
        client.send_sampler_stop()
        client.send_sampler_clear()
        client.send_sampler_register_variable(phase_ticks=0, period_ticks=2, address=123, size=4)
        client.send_sampler_start()
        yield from asyncio.sleep(0.1)
        asyncioloop.stop()
    asyncioloop.run_until_complete(test())
    assert client.received_samples > 0
