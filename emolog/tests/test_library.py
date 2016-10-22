from io import BytesIO

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
    msg = emolog.emo_decode(encoded)
    assert isinstance(msg, reply_class), "expected {}, got {}".format(reply_class, str(msg))


def test_client_parser():
    serial = BytesIO()
    parser = emolog.Parser(serial)
