"""
Wrap emolog c library. Build it if it doesn't exist. Provides the same
API otherwise, plus helpers.
"""

import ctypes
import os
import struct
import sys
from functools import wraps


__all__ = ['WPP_MESSAGE_TYPE_VERSION',
           'decode_emo_header',
           'encode_version',
           'write_version',
           'ClientParser',
           'Version',
           'Ack',
           'Ping',
           'SamplerSample',
           'SamplerRegisterVariable',
           'SamplerClear',
           'SamplerStart',
           'SamplerStop',
           'SamplerEnd']



if 'win' in sys.platform:
    LIBRARY_PATH = 'emolog.dll'
else:
    LIBRARY_PATH = 'libemolog.so'


def build_library():
    # chdir to path of module
    os.chdir(os.path.split(__file__)[0])
    os.system("make {}".format(LIBRARY_PATH))
    assert os.path.exists(LIBRARY_PATH)


def emolog():
    if not os.path.exists(LIBRARY_PATH):
        build_library()
    assert os.path.exists(LIBRARY_PATH)
    lib = ctypes.CDLL(os.path.join('.', LIBRARY_PATH))
    return lib


# importing builds!
lib = emolog()


### Globals

WPP_MESSAGE_TYPE_VERSION = 1
WPP_MESSAGE_TYPE_PING = 2
WPP_MESSAGE_TYPE_ACK = 3
WPP_MESSAGE_TYPE_SAMPLER_REGISTER_VARIABLE = 4
WPP_MESSAGE_TYPE_SAMPLER_CLEAR = 5
WPP_MESSAGE_TYPE_SAMPLER_START = 6
WPP_MESSAGE_TYPE_SAMPLER_STOP = 7
WPP_MESSAGE_TYPE_SAMPLER_SAMPLE = 8

header_size = 8

MAGIC_VALUES = list(map(ord, 'EM'))

### Messages


class Message(object):
    pass


class Version(Message):
    def __init__(self, version, reply_to_seq):
        self.version = version
        self.reply_to_seq = reply_to_seq


class Ping(Message):
    pass


class Ack(Message):
    def __init__(self, reply_to_seq):
        self.reply_to_seq = reply_to_seq


class SamplerRegisterVariable(Message):
    def __init__(self, phase_ticks, period_ticks, address, size):
        self.phase_ticks = phase_ticks
        self.period_ticks = period_ticks
        self.address = address
        self.size = size


class SamplerClear(Message):
    pass


class SamplerStart(Message):
    pass


class SamplerStop(Message):
    pass


class SamplerSample(Message):
    def __init__(self, ticks, **variables):
        """
        :param ticks:
        :param vars: dictionary from variable index to value
        :return:
        """
        self.ticks = ticks
        self.variables = variables


class MissingBytes(object):
    def __init__(self, needed):
        self.needed = needed


class SkipBytes(object):
    def __init__(self, skip):
        self.skip = skip


class UnknownMessage(object):
    def __init__(self, buf):
        self.buf = buf


### Code depending on lib

def dump_crctable():
    with open('crcdump.pickle', 'wb') as fd:
        fd.write(lib.crcTable, 256)


def get_seq():
    return lib.get_seq()


def decode_emo_header(s):
    """

    :param s: bytes of header
    :return: success (bool), message type (byte), payload length (uint16)
    """
    assert len(s) >= header_size
    m1, m2, t, l, seq, payload_crc, header_crc = struct.unpack('>BBBHBBB', s[:header_size])
    if [m1, m2] != MAGIC_VALUES:
        print("bad magic: {}, {} (expected {}, {})".format(m1, m2, *MAGIC_VALUES))
        return False, None, None
    print("got message: type {}, seq {}, length {}".format(t, seq, l))
    return True, t, l


class RegisteredVariable(object):
    def __init__(self, phase_ticks, period_ticks, address, size):
        self.phase_ticks = phase_ticks
        self.period_ticks = period_ticks
        self.address = address
        self.size = size


class VariableSampler(object):
    def __init__(self):
        self.table = []

    def clear(self):
        self.table.clear()

    def register_variable(self, phase_ticks, period_ticks, address, size):
        self.table.append(RegisteredVariable(phase_ticks=phase_ticks,
                                             period_ticks=period_ticks,
                                             address=address,
                                             size=size))

    def variables_from_ticks_and_payload(self, ticks, payload):
        variables = []
        offset = 0
        for row in self.table:
            if ticks % row.period_ticks == row.phase_ticks:
                variables.append(payload[offset:offset + row.size])
                offset += row.size
        return variables


variable_sampler = VariableSampler()


class ClientParser(object):
    def __init__(self):
        self.buf = b''

    def incoming(self, s):
        assert isinstance(s, bytes)
        self.buf = self.buf + s
        needed = lib.emo_decode(self.buf, len(self.buf))
        msg = None
        if needed == 0:
            valid, emo_type, emo_len = decode_emo_header(self.buf)
            payload = self.buf[header_size:]
            if emo_type == WPP_MESSAGE_TYPE_VERSION:
                (client_version, reply_to_seq, reserved) = struct.unpack('>HBB', payload)
                msg = Version(client_version, reply_to_seq)
            elif emo_type == WPP_MESSAGE_TYPE_ACK:
                (reply_to_seq,) = struct.unpack('<B', payload)
                msg = Ack(reply_to_seq)
            elif emo_type in [WPP_MESSAGE_TYPE_PING, WPP_MESSAGE_TYPE_SAMPLER_CLEAR, WPP_MESSAGE_TYPE_SAMPLER_START,
                              WPP_MESSAGE_TYPE_SAMPLER_STOP]:
                assert len(payload) == 0
                msg = {WPP_MESSAGE_TYPE_PING: Ping, WPP_MESSAGE_TYPE_SAMPLER_CLEAR: SamplerClear,
                       WPP_MESSAGE_TYPE_SAMPLER_START: SamplerStart, WPP_MESSAGE_TYPE_SAMPLER_STOP: SamplerStop}[emo_type]()
                if emo_type == WPP_MESSAGE_TYPE_SAMPLER_CLEAR:
                    variable_sampler.clear()
            elif emo_type == WPP_MESSAGE_TYPE_SAMPLER_REGISTER_VARIABLE:
                msg = SamplerRegisterVariable(*struct.unpack('>LLLH', payload))
                variable_sampler.register_variable(phase_ticks=msg.phase_ticks, period_ticks=msg.period_ticks,
                                                   address=msg.address, size=msg.size)
            elif emo_type == WPP_MESSAGE_TYPE_SAMPLER_SAMPLE:
                # TODO: this requires having a variable map so we can compute the variables from ticks
                ticks = struct.unpack('<L', payload[:4])[0]
                variables = variable_sampler.variables_from_ticks_and_payload(ticks, payload[4:])
                msg = SamplerSample(ticks=ticks, variables=variables)
            else:
                msg = UnknownMessage(buf)
            self.buf = b''
        elif needed > 0:
            msg = MissingBytes(needed)
        else:
            msg = SkipBytes(-needed)
        return msg

    def __str__(self):
        return '<ClientParser: #{}: {!r}'.format(len(self.buf), self.buf)

    __repr__ = __str__


def show_encoded(f):
    @wraps(f)
    def wrapped(*args, **kw):
        ret = f(*args, **kw)
        print("writing {} bytes: {}".format(len(ret), repr(ret)))
        return ret
    return wrapped


# Used by all encode functions - can segfault if buffer is too large
buf_size = 1024
buf = ctypes.create_string_buffer(buf_size)


@show_encoded
def encode_version():
    return buf[:lib.emo_encode_version(buf)]


@show_encoded
def encode_ping():
    return buf[:lib.emo_encode_ping(buf)]


@show_encoded
def encode_ack(reply_to_seq):
    return buf[:lib.emo_encode_ack(buf, reply_to_seq)]


@show_encoded
def encode_sampler_stop():
    return buf[:lib.emo_sampler_stop(buf)]


@show_encoded
def encode_sampler_start():
    return buf[:lib.emo_sampler_start(buf)]


@show_encoded
def encode_sampler_clear():
    return buf[:lib.emo_sampler_clear(buf)]


@show_encoded
def encode_sampler_stop():
    return buf[:lib.emo_sampler_register_variable(buf)]


def ctypes_mem_from_size_and_val(val, size):
    if size == 4:
        return ctypes.c_int32(val)
    elif size == 2:
        return ctypes.c_int16(val)
    elif size == 1:
        return ctypes.c_int8(val)
    raise Exception("unknown size {}".format(size))


@show_encoded
def encode_sampler_sample(ticks, var_size_pairs):
    lib.emo_sampler_sample_start(buf)
    for var, size in var_size_pairs:
        p = ctypes_mem_from_size_and_val(var, size)
        lib.emo_sampler_sample_add_var(ctypes.byref(var), )
    return buf[:lib.emo_sampler_sample_end(buf, ticks)]


@show_encoded
def encode_sampler_register_variable(phase_ticks, period_ticks, address, size):
    return buf[:lib.emo_sampler_register_variable(buf, phase_ticks, period_ticks, address, size)]


# Helpers to write messages to a file like object, like serial.Serial

def write_version(s):
    s.write(encode_version())
