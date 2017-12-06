import asyncio
from io import BytesIO
from socket import socketpair
import struct

import pytest

import emolog.lib as emolog


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
    msg, i_next, error = emolog.emo_decode(encoded, 0)
    assert isinstance(msg, reply_class), "expected {}, got {}".format(reply_class, str(msg))
    assert i_next == len(encoded)


def test_client_parser():
    serial = BytesIO()
    parser = emolog.Parser(serial)


def test_client_with_c_thing():
    # TODO
    pass



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

