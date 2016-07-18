"""
Wrap emolog c library. Build it if it doesn't exist. Provides the same
API otherwise, plus helpers.
"""

import ctypes
import os
import struct
import sys
from abc import ABCMeta, abstractmethod
from collections import defaultdict


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
    ret = os.system("make {}".format(LIBRARY_PATH))
    assert ret == 0, "make failed with error code {}, see above.".format(ret)
    assert os.path.exists(LIBRARY_PATH)


def emolog():
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
emo_message_type_to_str = {}

with open('emo_message_t.h') as fd:
    lines = [l.split('=') for l in fd.readlines() if l.strip() != '' and not l.strip().startswith('//')]
    lines = [(part_a.strip(), int(part_b.replace(',', '').strip())) for part_a, part_b in lines]
    for name, value in lines:
        assert(name.startswith('EMO_MESSAGE_TYPE_'))
        short_name = name[len('EMO_MESSAGE_TYPE_'):].lower()
        setattr(emo_message_types, short_name, value)
        emo_message_type_to_str[value] = short_name

header_size = 8

MAGIC_VALUES = list(map(ord, 'EM'))

### Messages


class Message(metaclass=ABCMeta):

    # Used by all encode functions - can segfault if buffer is too large
    buf_size = 1024
    buf = ctypes.create_string_buffer(buf_size)

    def __init__(self):
        pass

    @abstractmethod
    def encode_inner(self):
        pass

    def encode(self, **kw):
        s = self.buf[:self.encode_inner()]
        print("sending: {}, encoded as {}".format(self, s))
        return s

    def __str__(self):
        return '<{}>'.format(emo_message_type_to_str[self.type])

    __repr__ = __str__


class Version(Message):
    type = emo_message_types.version
    def __init__(self, version=None, reply_to_seq=None):
        self.version = version
        self.reply_to_seq = reply_to_seq

    def encode_inner(self):
        return lib.emo_encode_version(self.buf)


class Ping(Message):
    type = emo_message_types.ping
    def encode_inner(self):
        return lib.emo_encode_ping(self.buf)


class Ack(Message):
    type = emo_message_types.ack
    def __init__(self, error, reply_to_seq):
        self.error = error
        self.reply_to_seq = reply_to_seq

    def encode_inner(self):
        return lib.emo_encode_ack(self.buf, self.error, self.reply_to_seq)

    def __str__(self):
        # TODO - string for error
        return '<{} {} {}>'.format('ack' if self.error == 0 else 'nack', self.reply_to_seq, self.error)

    __repr__ = __str__


class SamplerRegisterVariable(Message):
    type = emo_message_types.sampler_register_variable
    def __init__(self, phase_ticks, period_ticks, address, size):
        assert size is not None
        self.phase_ticks = phase_ticks
        self.period_ticks = period_ticks
        self.address = address
        self.size = size

    def encode_inner(self):
        return lib.emo_encode_sampler_register_variable(self.buf,
                                                     ctypes.c_uint32(self.phase_ticks),
                                                     ctypes.c_uint32(self.period_ticks),
                                                     ctypes.c_uint32(self.address),
                                                     ctypes.c_uint16(self.size))

class SamplerClear(Message):
    type = emo_message_types.sampler_clear

    def encode_inner(self):
        return lib.emo_encode_sampler_clear(self.buf)


class SamplerStart(Message):
    type = emo_message_types.sampler_start

    def encode_inner(self):
        return lib.emo_encode_sampler_start(self.buf)


class SamplerStop(Message):
    type = emo_message_types.sampler_stop

    def encode_inner(self):
        return lib.emo_encode_sampler_stop(self.buf)


class SamplerSample(Message):
    type = emo_message_types.sampler_sample
    def __init__(self, ticks, payload=None, var_size_pairs=None):
        """
        :param ticks:
        :param vars: dictionary from variable index to value
        :return:
        """
        self.ticks = ticks
        self.payload = payload
        self.var_size_pairs = var_size_pairs
        self.variables = None

    def encode_inner(self):
        lib.emo_encode_sampler_sample_start(self.buf)
        for var, size in self.var_size_pairs:
            p = ctypes_mem_from_size_and_val(var, size)
            lib.emo_encode_sampler_sample_add_var(self.buf, ctypes.byref(p), size)
        return lib.emo_encode_sampler_sample_end(self.buf, self.ticks)

    def update_with_sampler(self, sampler):
        self.variables = sampler.variables_from_ticks_and_payload(ticks=self.ticks, payload=self.payload)

    def __str__(self):
        if self.variables:
            return '<sample {} variables {}>'.format(self.ticks, repr(self.variables))
        elif self.payload:
            return '<sample {} undecoded {}>'.format(self.ticks, repr(self.payload))
        elif self.var_size_pairs:
            return '<sample {} var_size_pairs {}>'.format(self.ticks, self.var_size_pairs)
        else:
            return '<sample {} error>'.format(self.ticks)

    __repr__ = __str__


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
    def __init__(self, type, buf):
        self.type = type
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


class HostSampler(object):

    def __init__(self, parser):
        self.parser = parser
        self.sampler = VariableSampler()

    def set_variables(self, vars):
        self.parser.send_command(SamplerClear())
        self.sampler.clear()
        for d in vars:
            self.sampler.register_variable(**d)
            self.register_variable(**d)
        self.parser.send_command(SamplerStart())

    def register_variable(self, phase_ticks, period_ticks, address, size):
        self.parser.send_command(SamplerRegisterVariable(
            phase_ticks=phase_ticks, period_ticks=period_ticks, address=address, size=size))

    def read_samples(self):
        while True:
            msg = self.parser.read_one()
            if isinstance(msg, SamplerSample):
                msg.update_with_sampler(self.sampler)
                yield msg
            else:
                print("ignoring a {}".format(msg))

    def stop(self):
        self.parser.send_command(SamplerStop())


def emo_decode(buf):
    needed = lib.emo_decode(buf, len(buf))
    msg = None
    if needed == 0:
        valid, emo_type, emo_len = decode_emo_header(buf)
        payload = buf[header_size:]
        if emo_type == emo_message_types.version:
            (client_version, reply_to_seq, reserved) = struct.unpack(endianess + 'HBB', payload)
            msg = Version(client_version, reply_to_seq)
        elif emo_type == emo_message_types.ack:
            (error, reply_to_seq) = struct.unpack(endianess + 'HB', payload)
            msg = Ack(error, reply_to_seq)
        elif emo_type in [emo_message_types.ping, emo_message_types.sampler_clear,
                          emo_message_types.sampler_start, emo_message_types.sampler_stop]:
            assert len(payload) == 0
            msg = {emo_message_types.ping: Ping,
                   emo_message_types.sampler_clear: SamplerClear,
                   emo_message_types.sampler_start: SamplerStart,
                   emo_message_types.sampler_stop: SamplerStop}[emo_type]()
        elif emo_type == emo_message_types.sampler_register_variable:
            msg = SamplerRegisterVariable(*struct.unpack(endianess + 'LLLHH', payload)[:4])
        elif emo_type == emo_message_types.sampler_sample:
            # TODO: this requires having a variable map so we can compute the variables from ticks
            ticks = struct.unpack(endianess + 'L', payload[:4])[0]
            msg = SamplerSample(ticks=ticks, payload=payload[4:])
        else:
            msg = UnknownMessage(type=emo_type, buf=Message.buf)
    elif needed > 0:
        msg = MissingBytes(message=buf, header=buf[:header_size], needed=needed)
    else:
        msg = SkipBytes(-needed)
    return msg


class ClientParser(object):
    def __init__(self, serial):
        self.buf = b''
        self.serial = serial
        self.ignored = defaultdict(int)
        self.sampler = VariableSampler()

    def _read_available(self):
        s = self.serial.read()
        assert isinstance(s, bytes)
        self.buf = self.buf + s
        needed = lib.emo_decode(self.buf, len(self.buf))
        msg = emo_decode(self.buf)
        if isinstance(msg, MissingBytes):
            pass
        elif isinstance(msg, SkipBytes):
            pass
        else:
            self.buf = b''
        if isinstance(msg, VariableSampler):
            self.sampler.clear()
        elif isinstance(msg, SamplerRegisterVariable):
            self.sampler.register_variable(phase_ticks=msg.phase_ticks, period_ticks=msg.period_ticks,
                                               address=msg.address, size=msg.size)
        elif isinstance(msg, SamplerSample):
            msg.update_with_sampler(self.sampler)
        return msg

    def send_command(self, command):
        """
        Sends a command to the client and waits for a reply and returns it.
        Blocking.
        """
        self.serial.write(command.encode())
        msg = self.read_one()
        print("Got {}".format(msg))
        if isinstance(msg, Version):
            return msg
        elif isinstance(msg, SamplerSample):
            # client is still sending samples, ignore silently
            self.ignored[msg.__class__] += 1
        else:
            assert isinstance(msg, Ack)
            #print("Got Ack")
            if msg.error != 0:
                print("client responded to {} with ERROR: {}".format(msg.reply_to_seq, msg.error))

    def read_one(self):
        # TOOD: timeout
        assert(len(self.buf) == 0)
        while True:
            msg = self._read_available()
            if isinstance(msg, SkipBytes):
                print("communication error - skipping bytes: {}".format(msg.skip))
                self.buf = self.buf[msg.skip:]
            elif isinstance(msg, MissingBytes):
                continue
            elif msg is not None:
                break
        return msg

    def __str__(self):
        return '<ClientParser: #{}: {!r}'.format(len(self.buf), self.buf)

    __repr__ = __str__


def ctypes_mem_from_size_and_val(val, size):
    if size == 4:
        return ctypes.c_int32(val)
    elif size == 2:
        return ctypes.c_int16(val)
    elif size == 1:
        return ctypes.c_int8(val)
    raise Exception("unknown size {}".format(size))
