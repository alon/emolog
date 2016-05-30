"""
Wrap emolog c library. Build it if it doesn't exist. Provides the same
API otherwise, plus helpers.
"""

import ctypes
import os
import struct
import sys
from functools import wraps


__all__ = ['EMO_MESSAGE_TYPE_VERSION',
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

# use big endian ('>') once TI/CCS htons is working
endianess = '<'


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

lib.emo_decode.restype = ctypes.c_int16

### Globals

class EmoMessageTypes(object):
    pass

emo_message_types = EmoMessageTypes()

with open('emo_message_t.h') as fd:
    lines = [l.split('=') for l in fd.readlines() if l.strip() != '' and not l.strip().startswith('//')]
    lines = [(part_a.strip(), int(part_b.replace(',', '').strip())) for part_a, part_b in lines]
    for name, value in lines:
        assert(name.startswith('EMO_MESSAGE_TYPE_'))
        setattr(emo_message_types, name[len('EMO_MESSAGE_TYPE_'):].lower(), value)

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
    def __init__(self, message, header, needed):
        self.message = message
        self.needed = needed
        self.header = header

    def __str__(self):
        return "Message: {} {!r} Header: {} {!r}, Missing bytes: {}".format(len(self.message),
                                                                         self.message,
                                                                         len(self.header),
                                                                         self.header, self.needed)
    __repr__ = __str__


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
    m1, m2, t, l, seq, payload_crc, header_crc = struct.unpack(endianess + 'BBBHBBB', s[:header_size])
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


class HostSampler(object):

    def __init__(self, s):
        self.s = s
        self.sampler = VariableSampler()

    def set_variables(self, vars):
        write_sampler_clear(self.s)
        for phase_ticks, period_ticks, address, size in vars:
            self.register_variable(phase_ticks, period_ticks, address, size)
        write_sampler_start(self.s)

    def register_variable(self, phase_ticks, period_ticks, address, size):
        write_sampler_register_variable(self.s, phase_ticks, period_ticks, address, size)

    def read_samples(self, parser):
        while True:
            msg = parser.read_one(self.s)
            if isinstance(msg, SamplerSample):
                yield msg
            else:
                print("ignoring a {}".format(msg))


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
            if emo_type == emo_message_types.version:
                (client_version, reply_to_seq, reserved) = struct.unpack(endianess + 'HBB', payload)
                msg = Version(client_version, reply_to_seq)
            elif emo_type == emo_message_types.ack:
                (reply_to_seq,) = struct.unpack(endianess + 'B', payload)
                msg = Ack(reply_to_seq)
            elif emo_type in [emo_message_types.ping, emo_message_types.sampler_clear,
                               emo_message_types.sampler_start, emo_message_types.sampler_stop]:
                assert len(payload) == 0
                msg = {emo_message_types.ping: Ping,
                       emo_message_types.sampler_clear: SamplerClear,
                       emo_message_types.sampler_start: SamplerStart,
                       emo_message_types.sampler_stop: SamplerStop}[emo_type]()
                if emo_type == emo_message_types.sampler_clear:
                    variable_sampler.clear()
            elif emo_type == emo_message_types.sampler_register_variable:
                msg = SamplerRegisterVariable(*struct.unpack(endianess + 'LLLHH', payload)[:4])
                variable_sampler.register_variable(phase_ticks=msg.phase_ticks, period_ticks=msg.period_ticks,
                                                   address=msg.address, size=msg.size)
            elif emo_type == emo_message_types.sampler_sample:
                # TODO: this requires having a variable map so we can compute the variables from ticks
                ticks = struct.unpack(endianess + 'L', payload[:4])[0]
                variables = variable_sampler.variables_from_ticks_and_payload(ticks, payload[4:])
                msg = SamplerSample(ticks=ticks, variables=variables)
            else:
                msg = UnknownMessage(buf)
            self.buf = b''
        elif needed > 0:
            msg = MissingBytes(message=self.buf, header=self.buf[:header_size], needed=needed)
        else:
            msg = SkipBytes(-needed)
        return msg

    def read_one(self, serial):
        assert(len(self.buf) == 0)
        size = 1
        while True:
            msg = self.incoming(serial.read(size))
            if isinstance(msg, SkipBytes):
                print("communication error - skipping bytes: {}".format(msg.skip))
                self.buf = self.buf[msg.skip:]
            elif isinstance(msg, MissingBytes):
                #size = max(1, msg.needed)
                continue
            elif msg is not None:
                break
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
    return buf[:lib.emo_encode_sampler_stop(buf)]


@show_encoded
def encode_sampler_start():
    return buf[:lib.emo_encode_sampler_start(buf)]


@show_encoded
def encode_sampler_clear():
    return buf[:lib.emo_encode_sampler_clear(buf)]


@show_encoded
def encode_sampler_register_variable(phase_ticks, period_ticks, address, size):
    return buf[:lib.emo_encode_sampler_register_variable(buf,
                                                         ctypes.c_uint32(phase_ticks),
                                                         ctypes.c_uint32(period_ticks),
                                                         ctypes.c_uint32(address),
                                                         ctypes.c_uint16(size))]


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
    lib.emo_encode_sampler_sample_start(buf)
    for var, size in var_size_pairs:
        p = ctypes_mem_from_size_and_val(var, size)
        lib.emo_encode_sampler_sample_add_var(buf, ctypes.byref(p), size)
    return buf[:lib.emo_encode_sampler_sample_end(buf, ticks)]


# Helpers to write messages to a file like object, like serial.Serial

def write_version(s):
    s.write(encode_version())


def write_sampler_clear(s):
    s.write(encode_sampler_clear())

def write_sampler_start(s):
    s.write(encode_sampler_start())

def write_sampler_stop(s):
    s.write(encode_sampler_stop())


def write_sampler_register_variable(s, phase_ticks, period_ticks, address, size):
    s.write(encode_sampler_register_variable(phase_ticks=phase_ticks, period_ticks=period_ticks, address=address, size=size))
