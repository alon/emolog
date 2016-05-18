import unittest

import emolog


class TestEmolog(unittest.TestCase):

    def test_decode_sane(self):
        parser = emolog.ClientParser()
        for name, reply_class, params in [
            ('version', emolog.Version, {}),
            ('ping', emolog.Ping, {}),
            ('ack', emolog.Ack, {"reply_to_seq": 5}),
            ('sampler_start', emolog.SamplerStart, {}),
            ('sampler_stop', emolog.SamplerStop, {}),
            ('sampler_clear', emolog.SamplerClear, {}),
            ('sampler_register_variable', emolog.SamplerRegisterVariable,
             {}),
            ('sampler_sample', emolog.SamplerSample,
             {
                 "ticks": 4242,
                 "var_size_pairs": [(1234, 2), (5678, 4)]
             }),
            ]:
            encoded = getattr(emolog, 'encode_{}'.format(name))(**params)
            msg = parser.incoming(encoded)
            self.assertIsInstance(msg, reply_class)
