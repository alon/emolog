# cython: linetrace=True

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


Wrap emolog_protocol.cpp library. Build it if it doesn't exist. Provides the same
API otherwise, plus helpers.
"""

import sys
from abc import ABCMeta, abstractmethod
from math import sin
from time import time
from logging import getLogger
from struct import pack, unpack
from asyncio import Protocol, get_event_loop, Future, InvalidStateError, sleep
import csv
from functools import wraps

import builtins # profile will be here when run via kernprof

import cython

# TODO: line_profiler is not compatible with cython.
if 'profile' not in builtins.__dict__:
    def nop_decorator(f):
        return f
    builtins.__dict__['profile'] = nop_decorator


ENDIANESS = '<'


logger = getLogger('emolog')


### Wrap emolog_protocol.cpp

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
    #int16_t emo_decode(const uint8_t *src, uint16_t size);
    int16_t emo_decode_with_offset(const uint8_t *src, unsigned offset, uint16_t size);
    void crc_init();


cdef extern from "emolog_protocol.h":
    cdef cppclass emo_message_t:
        pass


cdef extern from "emolog_protocol.h" namespace "emo_message_t":
    cdef emo_message_t EMO_MESSAGE_TYPE_VERSION
    cdef emo_message_t EMO_MESSAGE_TYPE_PING
    cdef emo_message_t EMO_MESSAGE_TYPE_ACK
    cdef emo_message_t EMO_MESSAGE_TYPE_SAMPLER_REGISTER_VARIABLE
    cdef emo_message_t EMO_MESSAGE_TYPE_SAMPLER_CLEAR
    cdef emo_message_t EMO_MESSAGE_TYPE_SAMPLER_START
    cdef emo_message_t EMO_MESSAGE_TYPE_SAMPLER_STOP
    cdef emo_message_t EMO_MESSAGE_TYPE_SAMPLER_SAMPLE


### Initialize crc table for emolog
crc_init()


### Globals


class emo_message_types:
    version=<int>EMO_MESSAGE_TYPE_VERSION
    ping=<int>EMO_MESSAGE_TYPE_PING
    ack=<int>EMO_MESSAGE_TYPE_ACK
    sampler_register_variable=<int>EMO_MESSAGE_TYPE_SAMPLER_REGISTER_VARIABLE
    sampler_clear=<int>EMO_MESSAGE_TYPE_SAMPLER_CLEAR
    sampler_start=<int>EMO_MESSAGE_TYPE_SAMPLER_START
    sampler_stop=<int>EMO_MESSAGE_TYPE_SAMPLER_STOP
    sampler_sample=<int>EMO_MESSAGE_TYPE_SAMPLER_SAMPLE


emo_message_type_to_str = {v: v for k, v in emo_message_types.__dict__.items() if not k.startswith('__')}


cdef int HEADER_SIZE = 8  # TODO - check this for consistency with library (add a test)


MAGIC = unpack(ENDIANESS + 'H', b'EM')[0]

### Messages


class Message(metaclass=ABCMeta):
    # Used by all encode functions - can segfault if buffer is too small
    buf = b'\x00' * 1024  # create_string_buffer(buf_size)

    def __init__(self, seq):
        self.seq = seq

    @abstractmethod
    def encode_inner(self):
        pass

    def encode(self, **kw):
        s = self.buf[:self.encode_inner()]
        return s

    def handle_by(self, handler):
        #logger.debug(f"ignoring a {self}")
        pass

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
        return emo_encode_version(self.buf, self.reply_to_seq if self.reply_to_seq is not None else self.seq)

    def handle_by(self, handler):
        #logger.debug(f"Got Version: {self.version}")
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
            emo_encode_sampler_sample_add_var(self.buf, to_str(var, size), size)
        return emo_encode_sampler_sample_end(self.buf, self.ticks)

    def handle_by(self, handler):
        if handler.sampler.running:
            self.update_with_sampler(handler.sampler)
            handler.pending_samples.append((self.seq, self.ticks, self.variables))
            #logger.debug(f"Got Sample: {self}")
        else:
            #logger.debug("ignoring sample since PC sampler is not primed")
            pass

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

    def handle_by(self, handler):
        pass

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
    _magic, _type, length, seq, payload_crc, header_crc = unpack(HEADER_FORMAT, s)
    return _type, length, seq


def decode_emo_header(s):
    """
    Decode emolog header
    :param s: bytes of header
    :return: success (None if yes, string of error otherwise), message type (byte), payload length (uint16), message sequence (byte)
    """
    magic, _type, length, seq, payload_crc, header_crc = unpack(HEADER_FORMAT, s)
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


@cython.final
cdef class VariableSampler:
    cdef public list table
    cdef public bint running

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

    def variables_from_ticks_and_payload(self, int ticks, payload):
        variables = {}
        cdef int offset = 0
        for row in self.table:
            if ticks % row.period_ticks == row.phase_ticks:
                variables[row.name] = row._type(payload[offset:offset + row.size])
                offset += row.size
        return variables



cdef uint8_t *to_str(val, size):
    if size == 4:
        if isinstance(val, float):
            return pack('<f', val)
        else:
            return pack('<i', val)
    elif size == 2:
        return pack('<h', val)
    elif size == 1:
        return pack('<b', val)
    raise Exception("unknown size {}".format(size))


SAMPLER_SAMPLE_TICKS_FORMAT = ENDIANESS + 'L'

sampler_sample = SamplerSample(0, 0)

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
            ticks = unpack(SAMPLER_SAMPLE_TICKS_FORMAT, payload[:4])[0]
            sampler_sample.reset(seq=seq, ticks=ticks, payload=payload[4:])
            msg = sampler_sample
        elif emo_type == emo_message_types.version:
            (client_version, reply_to_seq, reserved) = unpack(ENDIANESS + 'HBB', payload)
            msg = Version(seq=seq, version=client_version, reply_to_seq=reply_to_seq)
        elif emo_type == emo_message_types.ack:
            (error, reply_to_seq) = unpack(ENDIANESS + 'HB', payload)
            msg = Ack(seq=seq, error=error, reply_to_seq=reply_to_seq)
        elif emo_type in [emo_message_types.ping, emo_message_types.sampler_clear,
                          emo_message_types.sampler_start, emo_message_types.sampler_stop]:
            assert len(payload) == 0
            msg = {emo_message_types.ping: Ping,
                   emo_message_types.sampler_clear: SamplerClear,
                   emo_message_types.sampler_start: SamplerStart,
                   emo_message_types.sampler_stop: SamplerStop}[emo_type](seq=seq)
        elif emo_type == emo_message_types.sampler_register_variable:
            phase_ticks, period_ticks, address, size, _reserved = unpack(ENDIANESS + 'LLLHH', payload)
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


class Parser(object):
    def __init__(self, transport, debug=False):
        self.transport = transport
        self.buf = b''
        self.send_seq = 0
        self.empty_count = 0

        # debug flags
        self.debug_message_encoding = debug
        self.debug_message_decoding = debug

    def iter_available_messages(self, s):
        assert isinstance(s, bytes)
        if len(s) == 0:
            self.empty_count += 1
            # stream closed - quit - but wait a bit to be sure
            if self.empty_count > 2:
                raise SystemExit()
        self.buf = self.buf + s
        i = 0
        buf = self.buf
        n = len(buf)
        while i < n:
            msg, i_next, error = emo_decode(buf, i_start=i)
            if error:
                logger.error(error)
            if self.debug_message_decoding:
                if error:
                    logger.error("decoding error, buf length {}, error: {}".format(n, error))
                elif not hasattr(msg, 'type'):
                    logger.debug("decoded {}".format(msg))
                else:
                    pass # TODO: return this but only when run with --debug - it is slow otherwise
                    #logger.debug("decoded header: type {}, len {}, seq {} (buf #{})".format(
                    #    emo_message_type_to_str[msg.type], i_next - i, msg.seq, n))
            if isinstance(msg, SkipBytes):
                parsed_buf = buf[i:i_next]
                logger.debug("communication error - skipped {} bytes: {}".format(msg.skip, parsed_buf))
            elif isinstance(msg, MissingBytes):
                break
            yield msg
            i = i_next
        self.buf = self.buf[i:]
        if len(self.buf) > 1024:
            print("WARNING: something is wrong with the packet decoding: {} bytes left (from {})".format(
                len(self.buf), len(self.buf) + i))

    def send_message(self, command_class, **kw):
        """
        Sends a command to the client and waits for a reply and returns it.
        Blocking.
        """
        command = command_class(seq=self.send_seq, **kw)
        self.send_seq += 1
        encoded = command.encode()
        if self.debug_message_encoding:
            logger.debug("sending: {}, encoded as {}".format(command, encoded))
        self.transport.write(encoded)

    def __str__(self):
        return '<Parser: #{}: {!r}'.format(len(self.buf), self.buf)

    __repr__ = __str__

#### FakeEmbedded


# we ignore address, and size is used to return the same size as requested
cdef struct Sine:
    # Sinus parameters
    float freq
    float amp
    float phase
    # Sampling parameters
    int period_ticks
    int phase_ticks
    int size
    int address


def make_sine():
    return Sine(size=4, address=7,
                           freq=50 + 50 * (5 / 10.0), amp=10 * 5, phase=0.05 * 5,
                           phase_ticks=10,
                           period_ticks=20)


cdef class FakeSineEmbeddedBase:
    """
    Implement a simple embedded side. We don't care about the addresses,
    just fake a sinus on each address, starting at t=phase_ticks when requested,
    having a frequency that rises. Actually I'll wing it - it's really just
    a source of signals for debugging:
        the protocol
        the GUI

    Also an example of how an embedded side behaves:
        Respond with ACK to everything
        Except to Version: respond with our Version

    !important! do not write to STDOUT - used in a pipe
    """

    VERSION = 1
    cdef Sine sines[10]
    cdef int sines_num;

    def __init__(self, ticks_per_second):
        self.ticks_per_second = ticks_per_second
        self.tick_time = 1.0 / (ticks_per_second if ticks_per_second > 0 else 20000)
        self.verbose = True
        self.parser = None
        self.sines_num = 0
        self.start_time = time()
        self.running = False
        self.ticks = 0
        self.eventloop = get_event_loop()

    def connection_made(self, transport):
        self.parser = Parser(transport, debug=self.verbose)

    def data_received(self, data):
        for msg in self.parser.iter_available_messages(data):
            self.handle_message(msg)

    def handle_message(self, msg):
        if not isinstance(msg, Message):
            return

        # handle everything except Version
        if isinstance(msg, SamplerClear):
            self.on_sampler_clear()
        elif isinstance(msg, SamplerStart):
            self.on_sampler_start()
        elif isinstance(msg, SamplerStop):
            self.on_sampler_stop()
        elif isinstance(msg, SamplerRegisterVariable):
            self.on_sampler_register_variable(msg)

        # reply with ACK to everything
        if isinstance(msg, Version):
            self.parser.send_message(Version, version=self.VERSION, reply_to_seq=msg.seq)
        else:
            self.parser.send_message(Ack, error=0, reply_to_seq=msg.seq)

    def on_sampler_clear(self):
        self.sines_num = 0

    def on_sampler_stop(self):
        self.running = False

    def on_sampler_start(self):
        self.running = True
        self.ticks = 0
        self.eventloop.call_later(0.0, self.handle_time_event)

    def on_sampler_register_variable(self, msg):
        phase_ticks, period_ticks, address, size = (
            msg.phase_ticks, msg.period_ticks, msg.address, msg.size)
        n = self.sines_num
        self.sines_num += 1
        self.sines[n] = Sine(size=size, address=address,
                           freq=50 + 50 * (n / 10.0), amp=10 * n, phase=0.05 * n,
                           phase_ticks=phase_ticks,
                           period_ticks=period_ticks)

    def handle_time_event(self):
        # ignore time for the ticks aspect - a tick is a call of this function.
        # easy.
        if not self.running:
            return
        self.ticks += 1
        t = self.ticks * self.tick_time
        var_size_pairs = []
        for i in range(self.sines_num):
            sine = self.sines[i]
            if self.ticks % sine.period_ticks == sine.phase_ticks:
                var_size_pairs.append((float(sine.amp * sin(sine.phase + sine.freq * t)), sine.size))
        # We could use the gcd to find the minimal tick size but this is good enough
        if len(var_size_pairs) > 0:
            self.parser.send_message(SamplerSample, ticks=self.ticks, var_size_pairs=var_size_pairs)
        dt = max(0.0, self.tick_time * self.ticks + self.start_time - time()) if self.ticks_per_second > 0.0 else 0
        self.eventloop.call_later(dt, self.handle_time_event)


class FakeSineEmbedded(FakeSineEmbeddedBase, Protocol):
    def __init__(self, ticks_per_second, **kw):
        FakeSineEmbeddedBase.__init__(self, ticks_per_second)
        Protocol.__init__(self, **kw)


##### Client

class Dumper:
    def write(self, b):
        sys.stdout.write(repr(b))

dumper = Dumper()


cdef class CyClientBase:
    """
    Note: removed handling of Acks
     - TODO

    Removed ignored message handling
     - TODO
    """

    ACK_TIMEOUT_SECONDS = 1.0
    ACK_TIMEOUT = 'ACK_TIMEOUT'
    cdef int received_samples
    cdef unsigned stopped

    def __init__(self, verbose=False, dump=None):
        self._futures = set()
        self.verbose = verbose
        self.sampler = VariableSampler()
        self.received_samples = 0
        self.pending_samples = []
        self.reset_ack()
        self.parser = None
        self.transport = None
        self.connection_made_future = self.add_future()
        self.stopped = 0
        if dump:
            self.dump = open(dump, 'wb')
        else:
            self.dump = None #dumper

    def reset_ack(self):
        self.ack = Future()
        self.set_future_result(self.ack, True)

    def dump_buf(self, buf):
        self.dump.write(pack('<fI', time(), len(buf)) + buf)
        #self.dump.flush()

    def exit_gracefully(self):
        self.stopped = 1
        self.cancel_all_futures()

    def cancel_all_futures(self):
        for f in self._futures:
            f.cancel()
        self._futures.clear()

    def add_future(self, timeout=None, timeout_result=None):
        f = Future()
        self._futures.add(f)
        if timeout is not None:
            async def set_result_after_timeout():
                await sleep(timeout)
                try:
                    self.set_future_result(f, timeout_result)
                except:
                    pass
            sleep_task = get_event_loop().create_task(set_result_after_timeout())
            self._futures.add(sleep_task)
        return f

    def set_future_result(self, future, result):
        try:
            future.set_result(result)
        except InvalidStateError:
            pass # silently swallow error, means a double set_result
        if future in self._futures:
            self._futures.remove(future)

    def connection_lost(self, exc):
        # generally, what do we want to do at this point? it could mean USB was unplugged, actually has to be? if client stops
        # this wouldn't happen - we wouldn't notice at this level. So quit?
        self._debug_log("serial connection_lost")
        # ?? asyncio.get_event_loop.stop()

    def pause_writing(self):
        # interesting?
        print("PAUSE WRITING {}".format(self.transport.get_write_buffer_size()))

    def resume_writing(self):
        # interesting?
        print("RESUME WRITING {}".format(self.transport.get_write_buffer_size()))

    def _debug_log(self, s):
        logger.debug(s)

    def connection_made(self, transport):
        self.transport = transport
        self.parser = Parser(transport, debug=self.verbose)
        self.set_future_result(self.connection_made_future, self)

    def send_message(self, msg_type, **kw):
        self.parser.send_message(msg_type, **kw)
        self.ack = self.add_future(timeout=self.ACK_TIMEOUT_SECONDS, timeout_result=self.ACK_TIMEOUT)

    def data_received(self, data):
        if self.stopped > 0:
            return
        if self.dump:
            self.dump_buf(data)
        for msg in self.parser.iter_available_messages(data):
            msg.handle_by(self)
        if len(self.pending_samples) > 0:
            self.handle_sampler_samples(self.pending_samples)
            self.received_samples += len(self.pending_samples)
            del self.pending_samples[:]

    def handle_sampler_samples(self, msgs):
        """
        Override me
        """
        pass


##### EmoTool

def coalesce_meth(hertz):
    """
    decorator to call real function.
    TODO: use async loop mechanism, since otherwise this ends up possibly forgetting
    the last point. Since we intend to work at 20000 Hz and look at seconds, this is
    not a real problem
    """
    dt = 1.0 / hertz
    def wrappee(f):
        last_time = [None]
        msgs = []
        @wraps(f)
        def wrapper(self, msg):
            msgs.append(msg)
            cur_time = time()
            lt = last_time[0]
            if lt is None or cur_time - lt >= dt:
                last_time[0] = cur_time
            else:
                return
            f(self, msgs)
            msgs.clear()
        return wrapper
    return wrappee


cdef class CyEmoToolClient(CyClientBase):
    cdef bint _running

    def __init__(self, verbose, dump, window):
        super().__init__(verbose=verbose, dump=dump)
        self.csv = None
        self.csv_filename = None
        self.first_ticks = None
        self.last_ticks = None
        self.min_ticks = None
        self.names = None
        self.samples_received = 0
        self.ticks_lost = 0
        self.max_ticks = None
        self._running = False
        self.fd = None
        self.window = window
        self._do_plot = True

    def reset(self, csv_filename, names, min_ticks, max_ticks, do_plot):
        self.csv = None
        self.csv_filename = csv_filename
        self.first_ticks = None
        self.last_ticks = None
        self.min_ticks = min_ticks
        self.names = names
        self.samples_received = 0
        self.ticks_lost = 0
        self.max_ticks = max_ticks
        self._running = True
        self._do_plot = do_plot

    cpdef bint running(self):
        return self._running

    cpdef long total_ticks(self):
        if self.first_ticks is None or self.last_ticks is None:
            return 0
        return self.last_ticks - self.first_ticks

    def initialize_file(self):
        if self.csv:
            return
        self.fd = open(self.csv_filename, 'w+')
        self.csv = csv.writer(self.fd, lineterminator='\n')
        self.csv.writerow(['sequence', 'ticks', 'timestamp'] + self.names)

    def stop(self):
        self._running = False

    def handle_sampler_samples(self, msgs):
        """
        Write to CSV, add points to plots
        :param msgs: [(seq, ticks, {name: value})]
        :return: None
        """
        if not self._running:
            return
        if not self.csv:
            self.initialize_file()
        # TODO - decode variables (integer/float) in emolog VariableSampler
        now = time() * 1000
        self.csv.writerows([[seq, ticks, now] +
                      [variables.get(name, '') for name in self.names] for seq, ticks, variables in msgs])
        self.fd.flush()
        if self.window and self._do_plot:
            for (_seq, ticks, variables) in msgs:
                self.do_plot((ticks, list((k, v) for (k, v) in variables.items() if type(v) == float)))
        self.samples_received += len(msgs)
        for seq, ticks, variables in msgs:
            if self.last_ticks is not None and ticks - self.last_ticks != self.min_ticks:
                print("{:8.5}: ticks jump {:6} -> {:6} [{:6}]".format(
                    now / 1000, self.last_ticks, ticks, ticks - self.last_ticks))
                self.ticks_lost += ticks - self.last_ticks - self.min_ticks
            self.last_ticks = ticks
        if self.first_ticks is None:
            self.first_ticks = self.last_ticks
        if self.max_ticks is not None and self.total_ticks() + 1 >= self.max_ticks:
            self.stop()

    @coalesce_meth(10) # Limit refreshes, they can be costly
    def do_plot(self, msgs):
        self.window.log_variables(msgs=msgs)
