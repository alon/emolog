"""
Emolog is a logging protocol for debugging embedded c programs.

It consists of:
    1. python high-level library (this)
    2. c library compilable both on linux/windows hosts and embedded targets

Usage for real life:
    1. link c library into your program
    2. call init
    3. select a serial channel for transport
    4. call handler on arriving data
    5. implement sending of response messages

Usage for testing purposes:
    1. TODO


Wrap emolog_protocol c library. Build it if it doesn't exist. Provides the same
API otherwise, plus helpers.
"""

import struct
from abc import ABCMeta, abstractmethod
from logging import getLogger
from ctypes import create_string_buffer
import ctypes

import builtins # profile will be here when run via kernprof

from .setup import is_development_package, build_protocol_library, PROTOCOL_LIB, EMO_MESSAGE_TYPE_H_FILENAME

if 'profile' not in builtins.__dict__:
    def nop_decorator(f):
        return f
    builtins.__dict__['profile'] = nop_decorator


ENDIANESS = '<'


logger = getLogger('emolog')


### Wrap emolog_protocol.c

ctypedef unsigned uint32_t
ctypedef unsigned short uint16_t
ctypedef short int16_t
ctypedef unsigned char uint8_t

cdef extern from "emolog_protocol.h":
    uint16_t emo_encode_version(uint8_t *dest, uint8_t reply_to_seq);
    uint16_t emo_encode_ping(uint8_t *dest);
    uint16_t emo_encode_ack(uint8_t *dest, uint8_t reply_to_seq, uint16_t error);
    uint16_t emo_encode_sampler_register_variable(uint8_t *dest, uint32_t phase_ticks,
    uint32_t period_ticks, uint32_t address, uint16_t size);
    uint16_t emo_encode_sampler_clear(uint8_t *dest);
    uint16_t emo_encode_sampler_start(uint8_t *dest);
    uint16_t emo_encode_sampler_stop(uint8_t *dest);
    void emo_encode_sampler_sample_start(uint8_t *dest);
    void emo_encode_sampler_sample_add_var(uint8_t *dest, const uint8_t *p, uint16_t size);
    uint16_t emo_encode_sampler_sample_end(uint8_t *dest, uint32_t ticks);
    int16_t emo_decode(const uint8_t *src, uint16_t size);
    int16_t emo_decode_with_offset(const uint8_t *src, unsigned offset, uint16_t size);
    void crc_init();



### Globals


class EmoMessageTypes(object):
    pass


emo_message_types = EmoMessageTypes()
emo_message_type_to_str = {}


def initialize_emo_message_type_to_str():
    with open(EMO_MESSAGE_TYPE_H_FILENAME) as fd:
        lines = [l.split('=') for l in fd.readlines() if l.strip() != '' and not l.strip().startswith('//')]
        lines = [(part_a.strip(), int(part_b.replace(',', '').strip())) for part_a, part_b in lines]
        for name, value in lines:
            assert(name.startswith('EMO_MESSAGE_TYPE_'))
            short_name = name[len('EMO_MESSAGE_TYPE_'):].lower()
            setattr(emo_message_types, short_name, value)
            emo_message_type_to_str[value] = short_name
initialize_emo_message_type_to_str()


HEADER_SIZE = 8  # TODO - check this for consistency with library (add a test)


MAGIC = struct.unpack(ENDIANESS + 'H', b'EM')[0]

### Messages


class Message(metaclass=ABCMeta):

    # Used by all encode functions - can segfault if buffer is too small
    buf_size = 1024
    buf = create_string_buffer(buf_size)

    def __init__(self, seq):
        self.seq = seq

    @abstractmethod
    def encode_inner(self):
        pass

    def encode(self, **kw):
        s = self.buf[:self.encode_inner()]
        return s

    def handle_by(self, handler):
        logger.debug(f"ignoring a {self}")

    def __str__(self):
        return '<{}>'.format(emo_message_type_to_str[self.type])

    __repr__ = __str__


class Version(Message):
    type = emo_message_types.version
    def __init__(self, seq, version=None, reply_to_seq=None):
        super(Version, self).__init__(seq=seq)
        self.version = version
        self.reply_to_seq = reply_to_seq

    def encode_inner(self):
        return emo_encode_version(self.buf, self.reply_to_seq)

    def handle_by(self, handler):
        logger.debug(f"Got Version: {self.version}")
        handler.set_future_result(handler.ack, True)


class Ping(Message):
    type = emo_message_types.ping
    def encode_inner(self):
        return emo_encode_ping(self.buf)


class Ack(Message):
    type = emo_message_types.ack
    def __init__(self, seq, error, reply_to_seq):
        super(Ack, self).__init__(seq=seq)
        self.error = error
        self.reply_to_seq = reply_to_seq

    def encode_inner(self):
        return emo_encode_ack(self.buf, self.reply_to_seq, self.error)

    def handle_by(self, handler):
        if self.error != 0:
            logger.error(f"embedded responded to {self.reply_to_seq} with ERROR: {self.error}")
        handler.set_future_result(handler.ack, True)

    def __str__(self):
        # TODO - string for error
        return '<{} {} {}>'.format('ack' if self.error == 0 else 'nack', self.reply_to_seq, self.error)

    __repr__ = __str__


class SamplerRegisterVariable(Message):
    type = emo_message_types.sampler_register_variable

    def __init__(self, seq, phase_ticks, period_ticks, address, size):
        super(SamplerRegisterVariable, self).__init__(seq=seq)
        assert size is not None
        self.phase_ticks = phase_ticks
        self.period_ticks = period_ticks
        self.address = address
        self.size = size

    def encode_inner(self):
        return emo_encode_sampler_register_variable(self.buf,
                                                    self.phase_ticks,
                                                    self.period_ticks,
                                                    self.address,
                                                    self.size)

class SamplerClear(Message):
    type = emo_message_types.sampler_clear

    def encode_inner(self):
        return emo_encode_sampler_clear(self.buf)


class SamplerStart(Message):
    type = emo_message_types.sampler_start

    def encode_inner(self):
        return emo_encode_sampler_start(self.buf)


class SamplerStop(Message):
    type = emo_message_types.sampler_stop

    def encode_inner(self):
        return emo_encode_sampler_stop(self.buf)


class SamplerSample(Message):
    type = emo_message_types.sampler_sample

    def __init__(self, seq, ticks, payload=None, var_size_pairs=None):
        """
        :param ticks:
        :param vars: dictionary from variable index to value
        :return:
        """
        if var_size_pairs is None:
            var_size_pairs = []
        super().__init__(seq=seq)
        self.ticks = ticks
        self.payload = payload
        self.var_size_pairs = var_size_pairs
        self.variables = None

    def reset(self, seq, ticks, payload):
        self.seq = seq
        self.ticks = ticks
        self.payload = payload

    @classmethod
    def empty_size(cls):
        sample = cls(seq=0, ticks=0)
        return sample.encode_inner()

    def encode_inner(self):
        emo_encode_sampler_sample_start(self.buf)
        for var, size in self.var_size_pairs:
            p = ctypes_mem_from_size_and_val(var, size)
            emo_encode_sampler_sample_add_var(self.buf, p, size)
        return emo_encode_sampler_sample_end(self.buf, self.ticks)

    def handle_by(self, handler):
        if handler.sampler.running:
            self.update_with_sampler(handler.sampler)
            handler.received_samples += 1
            handler.pending_samples.append((self.seq, self.ticks, self.variables))
            logger.debug(f"Got Sample: {self}")
        else:
            logger.debug("ignoring sample since PC sampler is not primed")

    def update_with_sampler(self, sampler):
        self.variables = sampler.variables_from_ticks_and_payload(ticks=self.ticks, payload=self.payload)

    def __str__(self):
        if self.variables:
            return '<sample {} variables {}>'.format(self.ticks, repr(self.variables))
        elif self.var_size_pairs is not None:
            assert self.payload is None
            return '<sample {} var_size_pairs {}>'.format(self.ticks, self.var_size_pairs)
        elif self.payload is not None:
            return '<sample {} undecoded {}>'.format(self.ticks, repr(self.payload))
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

    def __str__(self):
        return "Skip Bytes {}".format(self.skip)

    __repr__ = __str__


class UnknownMessage(object):
    def __init__(self, type, buf):
        self.type = type
        self.buf = buf

    def __str__(self):
        return "Unknown Message type={} buf={}".format(self.type, self.byte)

    __repr__ = __str__


### Code depending on lib

# def dump_crctable():
#     with open('crcdump.pickle', 'wb') as fd:
#         fd.write(lib.crcTable, 256)
#

HEADER_FORMAT = ENDIANESS + 'HBHBBB'


def decode_emo_header_unsafe(s):
    """
    Decode emolog header assuming the MAGIC is correct
    :param s: bytes of header
    :return: success (None if yes, string of error otherwise), message type (byte), payload length (uint16), message sequence (byte)
    """
    _magic, _type, length, seq, payload_crc, header_crc = struct.unpack(HEADER_FORMAT, s)
    return _type, length, seq


def decode_emo_header(s):
    """
    Decode emolog header
    :param s: bytes of header
    :return: success (None if yes, string of error otherwise), message type (byte), payload length (uint16), message sequence (byte)
    """
    magic, _type, length, seq, payload_crc, header_crc = struct.unpack(HEADER_FORMAT, s)
    if magic != MAGIC:
        error = "bad magic: {} (expected {})".format(magic, MAGIC)
        return error, None, None, None
    return None, _type, length, seq


class RegisteredVariable(object):
    def __init__(self, name, phase_ticks, period_ticks, address, size, _type):
        self.name = name
        self.phase_ticks = phase_ticks
        self.period_ticks = period_ticks
        self.address = address
        self.size = size
        self._type = _type


class VariableSampler(object):
    def __init__(self):
        self.table = []
        self.running = False

    def clear(self):
        self.table.clear()

    def on_started(self):
        self.running = True

    def on_stopped(self):
        self.running = False

    def register_variable(self, name, phase_ticks, period_ticks, address, size, _type):
        self.table.append(RegisteredVariable(
            name=name,
            phase_ticks=phase_ticks,
            period_ticks=period_ticks,
            address=address,
            size=size,
            _type=_type))

    def variables_from_ticks_and_payload(self, ticks, payload):
        variables = {}
        offset = 0
        for row in self.table:
            if ticks % row.period_ticks == row.phase_ticks:
                variables[row.name] = row._type(payload[offset:offset + row.size])
                offset += row.size
        return variables



def ctypes_mem_from_size_and_val(val, size):
    if size == 4:
        if isinstance(val, float):
            return ctypes.c_float(val)
        else:
            return ctypes.c_int32(val)
    elif size == 2:
        return ctypes.c_int16(val)
    elif size == 1:
        return ctypes.c_int8(val)
    raise Exception("unknown size {}".format(size))


SAMPLER_SAMPLE_TICKS_FORMAT = ENDIANESS + 'L'


def emo_decode(buf, i_start):
    n = len(buf)
    needed = emo_decode_with_offset(buf, i_start, min(n - i_start, 0xffff))
    error = None
    if needed == 0:
        payload_start = i_start + HEADER_SIZE
        header = buf[i_start : payload_start]
        emo_type, emo_len, seq = decode_emo_header_unsafe(header)
        i_next = payload_start + emo_len
        payload = buf[payload_start : i_next]
        if emo_type == emo_message_types.sampler_sample:
            # TODO: this requires having a variable map so we can compute the variables from ticks
            ticks = struct.unpack(SAMPLER_SAMPLE_TICKS_FORMAT, payload[:4])[0]
            msg = SamplerSample(seq=seq, ticks=ticks, payload=payload[4:])
        elif emo_type == emo_message_types.version:
            (client_version, reply_to_seq, reserved) = struct.unpack(ENDIANESS + 'HBB', payload)
            msg = Version(seq=seq, version=client_version, reply_to_seq=reply_to_seq)
        elif emo_type == emo_message_types.ack:
            (error, reply_to_seq) = struct.unpack(ENDIANESS + 'HB', payload)
            msg = Ack(seq=seq, error=error, reply_to_seq=reply_to_seq)
        elif emo_type in [emo_message_types.ping, emo_message_types.sampler_clear,
                          emo_message_types.sampler_start, emo_message_types.sampler_stop]:
            assert len(payload) == 0
            msg = {emo_message_types.ping: Ping,
                   emo_message_types.sampler_clear: SamplerClear,
                   emo_message_types.sampler_start: SamplerStart,
                   emo_message_types.sampler_stop: SamplerStop}[emo_type](seq=seq)
        elif emo_type == emo_message_types.sampler_register_variable:
            phase_ticks, period_ticks, address, size, _reserved = struct.unpack(ENDIANESS + 'LLLHH', payload)
            msg = SamplerRegisterVariable(seq=seq, phase_ticks=phase_ticks, period_ticks=period_ticks,
                                          address=address, size=size)
        else:
            msg = UnknownMessage(seq=seq, type=emo_type, buf=Message.buf)
    elif needed > 0:
        msg = MissingBytes(message=buf, header=buf[i_start : i_start + HEADER_SIZE], needed=needed)
        i_next = i_start + needed
    else:
        msg = SkipBytes(-needed)
        i_next = i_start - needed
    return msg, i_next, error


class AckTimeout(Exception):
    pass


