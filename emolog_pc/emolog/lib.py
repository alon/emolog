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

import asyncio
from asyncio import Future
from asyncio.futures import InvalidStateError
from collections import namedtuple
from time import time
import ctypes
import os
import struct
import sys
from time import clock
from math import sin
from abc import ABCMeta, abstractmethod
import logging

from .util import which

import builtins # profile will be here when run via kernprof

if 'profile' not in builtins.__dict__:
    def nop_decorator(f):
        return f
    builtins.__dict__['profile'] = nop_decorator

__all__ = [
    'EMO_MESSAGE_TYPE_VERSION',
    'decode_emo_header_unsafe',
    'encode_version',
    'write_version',
    'Client',
    'Parser',
    'FakeSineEmbedded',
    'Version',
    'Ack',
    'Ping',
    'SamplerSample',
    'SamplerRegisterVariable',
    'SamplerClear',
    'SamplerStart',
    'SamplerStop',
    'SamplerEnd',
    'build_protocol_library',
    'LIB_FILENAME',
    'DEVEL_EMO_MESSAGE_TYPE_H_FILENAME',
]


ENDIANESS = '<'


logger = logging.getLogger('emolog')


if 'win' in sys.platform:
    LIB_RELATIVE_DIR = '../../emolog_protocol'
    LIB_FILENAME = 'emolog_protocol.dll'
    MAKE_EXEC = 'make.exe'
else:
    LIB_RELATIVE_DIR = '../../emolog_protocol'
    LIB_FILENAME = 'libemolog_protocol.so'
    MAKE_EXEC = 'make'
is_development_package = os.path.exists(os.path.join('..', '.git'))
module_dir = os.path.split(__file__)[0]

DEVEL_LIB_ABS_DIR = os.path.realpath(os.path.join(module_dir, LIB_RELATIVE_DIR))
DEVEL_PROTOCOL_LIB = os.path.join(DEVEL_LIB_ABS_DIR, LIB_FILENAME)
DEVEL_EMO_MESSAGE_TYPE_H_FILENAME = os.path.join(DEVEL_LIB_ABS_DIR, 'source/emo_message_t.h')

if is_development_package:
    LIB_ABS_DIR = DEVEL_LIB_ABS_DIR
    EMO_MESSAGE_TYPE_H_FILENAME = DEVEL_EMO_MESSAGE_TYPE_H_FILENAME
else:
    LIB_ABS_DIR = os.path.realpath(module_dir)
    EMO_MESSAGE_TYPE_H_FILENAME = os.path.join(LIB_ABS_DIR, 'emo_message_t.h')
PROTOCOL_LIB = os.path.join(LIB_ABS_DIR, LIB_FILENAME)


def build_protocol_library():
    # chdir to path of library
    orig_path = os.getcwd()
    if not os.path.exists(LIB_ABS_DIR):
        return # not actually a development checkout
    os.chdir(LIB_ABS_DIR)
    if not os.path.exists(LIB_FILENAME) or os.stat(LIB_FILENAME).st_mtime < os.stat('source/emolog_protocol.c').st_mtime:
        if which(MAKE_EXEC) is None:
            print("missing make; please place a copy of {} at {}".format(LIB_FILENAME, LIB_ABS_DIR))
            raise SystemExit
        ret = os.system("make {}".format(LIB_FILENAME))
        assert ret == 0, "make failed with error code {}, see above.".format(ret)
    assert os.path.exists(LIB_FILENAME)
    os.chdir(orig_path)
    return PROTOCOL_LIB


def emolog_lib():
    if is_development_package:
        build_protocol_library()
    assert os.path.exists(PROTOCOL_LIB), f"missing {PROTOCOL_LIB}"
    lib = ctypes.CDLL(PROTOCOL_LIB)
    lib.crc_init()
    return lib


# importing builds!
lib = emolog_lib()

lib.emo_decode_with_offset.restype = ctypes.c_int16


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
    buf = ctypes.create_string_buffer(buf_size)

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
        return lib.emo_encode_version(self.buf)

    def handle_by(self, handler):
        logger.debug(f"Got Version: {self.version}")
        handler.set_future_result(handler.ack, True)


class Ping(Message):
    type = emo_message_types.ping
    def encode_inner(self):
        return lib.emo_encode_ping(self.buf)


class Ack(Message):
    type = emo_message_types.ack
    def __init__(self, seq, error, reply_to_seq):
        super(Ack, self).__init__(seq=seq)
        self.error = error
        self.reply_to_seq = reply_to_seq

    def encode_inner(self):
        return lib.emo_encode_ack(self.buf, self.reply_to_seq, self.error)

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
        lib.emo_encode_sampler_sample_start(self.buf)
        for var, size in self.var_size_pairs:
            p = ctypes_mem_from_size_and_val(var, size)
            lib.emo_encode_sampler_sample_add_var(self.buf, ctypes.byref(p), size)
        return lib.emo_encode_sampler_sample_end(self.buf, self.ticks)

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

def dump_crctable():
    with open('crcdump.pickle', 'wb') as fd:
        fd.write(lib.crcTable, 256)


def get_seq():
    return lib.get_seq()


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


SAMPLER_SAMPLE_TICKS_FORMAT = ENDIANESS + 'L'


# in the interest of speed, we keep a single SamplerSample instance and reset it
sampler_sample = SamplerSample(0, 0, b'')


def emo_decode(buf, i_start):
    n = len(buf)
    needed = lib.emo_decode_with_offset(buf, i_start, min(n - i_start, 0xffff))
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
            sampler_sample.reset(seq=seq, ticks=ticks, payload=payload[4:])
            msg = sampler_sample # SamplerSample(seq=seq, ticks=ticks, payload=payload[4:])
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


def none_to_empty_buffer(item):
    if item is None:
        return b''
    return item


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
                    logger.debug("decoded header: type {}, len {}, seq {} (buf #{})".format(
                        emo_message_type_to_str[msg.type], i_next - i, msg.seq, n))
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


class AckTimeout(Exception):
    pass


class Dumper:
    def write(self, b):
        sys.stdout.write(repr(b))

dumper = Dumper()


class Client(asyncio.Protocol):
    """
    Note: removed handling of Acks
     - TODO

    Removed ignored message handling
     - TODO
    """

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
        self.stopped = False
        if dump:
            self.dump = open(dump, 'wb')
        else:
            self.dump = None #dumper

    def reset_ack(self):
        self.ack = Future()
        self.set_future_result(self.ack, True)

    def dump_buf(self, buf):
        self.dump.write(struct.pack('<fI', clock(), len(buf)) + buf)
        #self.dump.flush()

    def exit_gracefully(self):
        self.stopped = True
        self.cancel_all_futures()

    def cancel_all_futures(self):
        for f in self._futures:
            f.cancel()
        self._futures.clear()

    def add_future(self, timeout=None, timeout_result=None):
        f = asyncio.Future()
        self._futures.add(f)
        if timeout is not None:
            async def set_result_after_timeout():
                await asyncio.sleep(timeout)
                try:
                    self.set_future_result(f, timeout_result)
                except:
                    pass
            sleep_task = asyncio.get_event_loop().create_task(set_result_after_timeout())
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

    async def send_set_variables(self, variables):
        await self.send_sampler_clear()
        self.sampler.clear()
        for d in variables:
            self.sampler.register_variable(**d)
            await self.send_sampler_register_variable(
                phase_ticks=d['phase_ticks'],
                period_ticks=d['period_ticks'],
                address=d['address'],
                size=d['size']
            )

    async def send_sampler_clear(self):
        await self.send_and_ack(SamplerClear)

    async def send_sampler_register_variable(self, phase_ticks, period_ticks, address, size):
        await self.send_and_ack(SamplerRegisterVariable,
            phase_ticks=phase_ticks, period_ticks=period_ticks, address=address, size=size)

    async def send_sampler_clear(self):
        await self.send_and_ack(SamplerClear)

    async def send_sampler_start(self):
        await self.send_and_ack(SamplerStart)
        self.sampler.on_started()

    async def send_sampler_stop(self):
        await self.send_and_ack(SamplerStop)
        self.sampler.on_stopped()

    async def send_version(self):
        # We don't tell our version to the embedded right now - it doesn't care
        # anyway
        await self.send_after_last(Version)

    ACK_TIMEOUT_SECONDS = 1.0
    ACK_TIMEOUT = 'ACK_TIMEOUT'

    async def send_after_last(self, msg_type, **kw):
        """
        We are running in asyncio

        We must await an ack from the embedded. That is the protocol and
        importantly the embedded has a tiny 16 byte buffer so it cannot
        handle more than a message at a time.
        """
        await self.await_ack()
        self.send_message(msg_type, **kw)

    async def send_and_ack(self, msg_type, **kw):
        await self.send_after_last(msg_type, **kw)
        await self.await_ack()

    async def await_ack(self):
        await self.ack
        is_timeout = self.ack.result() == self.ACK_TIMEOUT
        self.reset_ack()
        if is_timeout:
            raise AckTimeout()

    def send_message(self, msg_type, **kw):
        self.parser.send_message(msg_type, **kw)
        self.ack = self.add_future(timeout=self.ACK_TIMEOUT_SECONDS, timeout_result=self.ACK_TIMEOUT)

    def data_received(self, data):
        if self.stopped:
            return
        if self.dump:
            self.dump_buf(data)
        for msg in self.parser.iter_available_messages(data):
            msg.handle_by(self)
        if len(self.pending_samples) > 0:
            self.handle_sampler_samples(self.pending_samples)
            del self.pending_samples[:]

    def handle_sampler_samples(self, msgs):
        """
        Override me
        """
        pass


class TransportFed(object):
    def __init__(self, writefd):
        self.data = []
        self.writefd = writefd

    def feed_me(self, s):
        self.data.append(s)

    def read(self):
        s = b''.join(reversed(self.data))
        self.data.clear()
        return s

    def write(self, s):
        self.writefd.write(s)


class TransportPairOfFd(object):
    def __init__(self, fdin, fdout):
        self.fdin = fdin
        self.fdout = fdout

    def write(self, s):
        self.fdout.write(s)

    def read(self):
        data = self.fdin.read()
        return data

    def fileno(self):
        """ used by Client to get the reader fileno """
        return self.fdin.fileno()


class TransportStdinAndOut(TransportPairOfFd):
    def __init__(self):
        super(TransportStdinAndOut, self).__init__(fdin=sys.stdin.buffer,
                                                   fdout=sys.stdout.buffer)


class ClientToFake(asyncio.SubprocessProtocol):
    """
    Implemented as an asyncio protocol over a subprocess.
    The subprocess runs the FakeSineEmbedded implementation below, but can
    later run a c program to simulate the ti-side with the same code, thereby
    testing it.
    """
    def __init__(self, eventloop, subprocess_cmdline=None):
        self.eventloop = eventloop
        if subprocess_cmdline is None:
            subprocess_cmdline = ["./embedded_sine.py"]
        self.subprocess_cmdline = subprocess_cmdline

    def initialize(self):
        embedded_process_create = self.eventloop.subprocess_exec(protocol_factory=lambda: self,
                                                                 program=self.subprocess_cmdline[0],
                                                                 *self.subprocess_cmdline[1:])
        transport, protocol = yield from embedded_process_create
        logger.debug("ClientToFake: transport={}, protocol={}".format(transport, protocol))
        self.transport = TransportFed(transport.get_pipe_transport(0))
        # you need
        raise NotImplementedError()
        self.client = Client()

    def pipe_data_received(self, fd, data):
        logger.debug("ClientToFake: got data {!r}".format(data))
        self.transport.feed_me(data)
        self.client.handle_transport_ready_for_read()

    def process_exited(self):
        logger.debug("subprocess has quit")


class FakeSineEmbedded(asyncio.Protocol):
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

    # we ignore address, and size is used to return the same size as requested
    Sine = namedtuple('Sine', [
        # Sinus parameters
        'freq', 'amp', 'phase',
        # Sampling parameters
        'period_ticks', 'phase_ticks', 'size', 'address'])

    def __init__(self, ticks_per_second, **kw):
        super().__init__(**kw)
        self.ticks_per_second = ticks_per_second
        self.tick_time = 1.0 / ticks_per_second
        self.verbose = True
        self.parser = None
        self.sines = []
        self.start_time = time()
        self.running = False
        self.ticks = 0
        self.eventloop = asyncio.get_event_loop()

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
        self.sines.clear()

    def on_sampler_stop(self):
        self.running = False

    def on_sampler_start(self):
        self.running = True
        self.ticks = 0
        self.eventloop.call_later(0.0, self.handle_time_event)

    def on_sampler_register_variable(self, msg):
        phase_ticks, period_ticks, address, size = (
            msg.phase_ticks, msg.period_ticks, msg.address, msg.size)
        n = len(self.sines) + 1
        self.sines.append(self.Sine(size=size, address=address,
                               freq=50 + 50 * (n / 10.0), amp=10 * n, phase=0.05 * n,
                               phase_ticks=phase_ticks,
                               period_ticks=period_ticks))

    def handle_time_event(self):
        # ignore time for the ticks aspect - a tick is a call of this function.
        # easy.
        if not self.running:
            return
        self.ticks += 1
        t = self.ticks * self.tick_time
        var_size_pairs = []
        for sine in self.sines:
            if self.ticks % sine.period_ticks == sine.phase_ticks:
                var_size_pairs.append((float(sine.amp * sin(sine.phase + sine.freq * t)), sine.size))
        # We could use the gcd to find the minimal tick size but this is good enough
        if len(var_size_pairs) > 0:
            self.parser.send_message(SamplerSample, ticks=self.ticks, var_size_pairs=var_size_pairs)
        dt = max(0.0, self.tick_time * self.ticks + self.start_time - time())
        self.eventloop.call_later(dt, self.handle_time_event)


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
