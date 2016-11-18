"""
Emolog is a logging protocol for debugging embedded c programs.

It consists of:
    1. python high-level library (this)
    2. c library compilable on for linux/windows hosts and TI embedded target

Usage for real life:
    1. link c library into your program
    2. call init
    3. select a serial channel for transport,
    4. call handler on arriving data
    5. implement sending of response messages

Usage for testing purposes:
    1. TODO


Wrap emolog c library. Build it if it doesn't exist. Provides the same
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


__all__ = ['EMO_MESSAGE_TYPE_VERSION',
           'decode_emo_header',
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
           'SocketToFile',
           'AsyncIOEventLoop',
           ]


endianess = '<'


logger = logging.getLogger('emolog')


if 'win' in sys.platform:
    LIBRARY_PATH = 'emolog.dll'
else:
    LIBRARY_PATH = 'libemolog.so'


def build_library():
    # chdir to path of module
    os.chdir(os.path.split(__file__)[0])
    if not os.path.exists(LIBRARY_PATH) or os.stat(LIBRARY_PATH).st_mtime < os.stat('emolog.c').st_mtime:
        ret = os.system("make {} 2>&1 > /dev/null".format(LIBRARY_PATH))
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
        super(SamplerSample, self).__init__(seq=seq)
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


def decode_emo_header(s):
    """
    Decode emolog header
    :param s: bytes of header
    :return: success (None if yes, string of error otherwise), message type (byte), payload length (uint16), message sequence (byte)
    """
    assert len(s) >= header_size
    m1, m2, _type, length, seq, payload_crc, header_crc = struct.unpack(endianess + 'BBBHBBB', s[:header_size])
    if [m1, m2] != MAGIC_VALUES:
        error = "bad magic: {}, {} (expected {}, {})".format(m1, m2, *MAGIC_VALUES)
        return error, None, None, None
    return None, _type, length, seq


class RegisteredVariable(object):
    def __init__(self, phase_ticks, period_ticks, address, size, _type):
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

    def register_variable(self, phase_ticks, period_ticks, address, size, _type):
        self.table.append(RegisteredVariable(phase_ticks=phase_ticks,
                                             period_ticks=period_ticks,
                                             address=address,
                                             size=size,
                                             _type=_type))

    def variables_from_ticks_and_payload(self, ticks, payload):
        variables = []
        offset = 0
        for row in self.table:
            if ticks % row.period_ticks == row.phase_ticks:
                variables.append(row._type(payload[offset:offset + row.size]))
                offset += row.size
        return variables


def emo_decode(buf):
    needed = lib.emo_decode(buf, len(buf))
    msg = None
    error = None
    if needed == 0:
        error, emo_type, emo_len, seq = decode_emo_header(buf)
        if error:
            return None, buf[1:], error
        payload = buf[header_size:header_size + emo_len]
        buf = buf[header_size + emo_len:]
        if emo_type == emo_message_types.version:
            (client_version, reply_to_seq, reserved) = struct.unpack(endianess + 'HBB', payload)
            msg = Version(seq=seq, version=client_version, reply_to_seq=reply_to_seq)
        elif emo_type == emo_message_types.ack:
            (error, reply_to_seq) = struct.unpack(endianess + 'HB', payload)
            msg = Ack(seq=seq, error=error, reply_to_seq=reply_to_seq)
        elif emo_type in [emo_message_types.ping, emo_message_types.sampler_clear,
                          emo_message_types.sampler_start, emo_message_types.sampler_stop]:
            assert len(payload) == 0
            msg = {emo_message_types.ping: Ping,
                   emo_message_types.sampler_clear: SamplerClear,
                   emo_message_types.sampler_start: SamplerStart,
                   emo_message_types.sampler_stop: SamplerStop}[emo_type](seq=seq)
        elif emo_type == emo_message_types.sampler_register_variable:
            phase_ticks, period_ticks, address, size, _reserved = struct.unpack(endianess + 'LLLHH', payload)
            msg = SamplerRegisterVariable(seq=seq, phase_ticks=phase_ticks, period_ticks=period_ticks,
                                          address=address, size=size)
        elif emo_type == emo_message_types.sampler_sample:
            # TODO: this requires having a variable map so we can compute the variables from ticks
            ticks = struct.unpack(endianess + 'L', payload[:4])[0]
            msg = SamplerSample(seq=seq, ticks=ticks, payload=payload[4:])
        else:
            msg = UnknownMessage(seq=seq, type=emo_type, buf=Message.buf)
    elif needed > 0:
        msg = MissingBytes(message=buf, header=buf[:header_size], needed=needed)
    else:
        msg = SkipBytes(-needed)
        buf = buf[-needed:]
    return msg, buf, error


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
        while len(self.buf) > 0:
            msg, left_over_buf, error = emo_decode(self.buf)
            if error:
                logger.error(error)
            if self.debug_message_decoding:
                if error:
                    logger.error("decoding error, buf length {}, error: {}".format(
                        len(self.buf), error))
                elif not hasattr(msg, 'type'):
                    logger.debug("decoded {}".format(msg))
                else:
                    logger.debug("decoded header: type {}, len {}, seq {} (buf #{})".format(
                        emo_message_type_to_str[msg.type], len(self.buf) - len(left_over_buf), msg.seq,
                        len(self.buf)))
            parsed_buf = self.buf[:len(self.buf) - len(left_over_buf)]
            self.buf = left_over_buf
            if isinstance(msg, SkipBytes):
                logger.debug("communication error - skipped {} bytes: {}".format(msg.skip, parsed_buf))
            elif isinstance(msg, MissingBytes):
                break
            yield msg

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
        self.transport.write(command.encode())

    def __str__(self):
        return '<Parser: #{}: {!r}'.format(len(self.buf), self.buf)

    __repr__ = __str__


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
        self.acked = Future()
        self.acked.set_result(True)
        self.parser = None
        self.transport = None
        self.connection_made_future = self.add_future()
        self.stopped = False
        if dump:
            self.dump = open(dump, 'wb')
        else:
            self.dump = None

    def dump_buf(self, buf):
        self.dump.write(struct.pack('<fI', clock(), len(buf)) + buf)
        #self.dump.flush()

    def exit_gracefully(self):
        self.stopped = True
        self.cancel_all_futures()
        self.serial.abort()

    def cancel_all_futures(self):
        for f in self._futures:
            f.cancel()
        self._futures.clear()

    def add_future(self):
        f = asyncio.Future()
        self._futures.add(f)
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
        self._debug_log(self.transport.get_write_buffer_size())

    def resume_writing(self):
        # interesting?
        self._debug_log(self.transport.get_write_buffer_size())

    def _debug_log(self, s):
        logger.debug(s)

    def connection_made(self, transport):
        if hasattr(transport, 'serial'):
            # hack - should be done at the transport
            transport.serial.rts = False
        self.transport = transport
        self.parser = Parser(transport, debug=self.verbose)
        self.set_future_result(self.connection_made_future, self)

    async def send_set_variables(self, variables):
        await self.send_sampler_clear()
        self.sampler.clear()
        for d in variables:
            self.sampler.register_variable(**d)
            d_rest = dict(d)
            del d_rest['_type']
            await self.send_sampler_register_variable(**d_rest)

    async def send_sampler_clear(self):
        await self.send_after_last(SamplerClear)

    async def send_sampler_register_variable(self, phase_ticks, period_ticks, address, size):
        await self.send_after_last(SamplerRegisterVariable,
            phase_ticks=phase_ticks, period_ticks=period_ticks, address=address, size=size)

    async def send_sampler_clear(self):
        await self.send_after_last(SamplerClear)

    async def send_sampler_start(self):
        await self.send_after_last(SamplerStart)
        self.sampler.on_started()

    async def send_sampler_stop(self):
        await self.send_after_last(SamplerStop)
        self.sampler.on_stopped()

    async def send_version(self):
        # We don't tell our version to the embedded right now - it doesn't care
        # anyway
        await self.send_after_last(Version)

    async def stop(self):
        await self.send_after_last(SamplerStop)

    async def send_after_last(self, msg_type, **kw):
        """
        We are running in asyncio

        We must await an ack from the embedded. That is the protocol and
        importantly the embedded has a tiny 16 byte buffer so it cannot
        handle more than a message at a time.
        """
        await self.acked
        self.send_message(msg_type, **kw)

    def send_message(self, msg_type, **kw):
        self.parser.send_message(msg_type, **kw)
        self.acked = self.add_future()

    def data_received(self, data):
        if self.stopped:
            return
        if self.dump:
            self.dump_buf(data)
        for msg in self.parser.iter_available_messages(data):
            self.handle_message(msg)

    def handle_message(self, msg):
        if isinstance(msg, Version):
            logger.debug("Got Version: {}".format(msg.version))
            self.set_future_result(self.acked, True)
        elif isinstance(msg, SamplerSample):
            if self.sampler.running:
                msg.update_with_sampler(self.sampler)
                self.received_samples += 1
                logger.debug("Got Sample: {}".format(msg))
                self.handle_sampler_sample(msg)
            else:
                logger.debug("ignoring sample since PC sampler is not primed")
        elif isinstance(msg, Ack):
            if msg.error != 0:
                logger.error("embedded responded to {} with ERROR: {}".format(msg.reply_to_seq, msg.error))
            self.set_future_result(self.acked, True)
        else:
            logger.debug("ignoring a {}".format(msg))

    def handle_sampler_sample(self, msg):
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
    TICK_TIME = 0.00001 # 10kHz - enough for testing I hope.

    # we ignore address, and size is used to return the same size as requested
    Sine = namedtuple('Sine', [
        # Sinus parameters
        'freq', 'amp', 'phase',
        # Sampling parameters
        'period_ticks', 'phase_ticks', 'size', 'address'])

    def __init__(self, *args, **kw):
        super(FakeSineEmbedded, self).__init__(*args, **kw)
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
        self.sines.append(self.Sine(size=size, address=address,
                               freq=100, amp=100, phase=0.0,
                               phase_ticks=phase_ticks,
                               period_ticks=period_ticks))

    def handle_time_event(self):
        # ignore time for the ticks aspect - a tick is a call of this function.
        # easy.
        if not self.running:
            return
        self.ticks += 1
        t = time() - self.start_time
        var_size_pairs = []
        for sine in self.sines:
            if self.ticks % sine.period_ticks == sine.phase_ticks:
                var_size_pairs.append((int(sine.amp * sin(sine.phase + sine.freq * t)), sine.size))
        # We could use the gcd to find the minimal tick size but this is good enough
        if len(var_size_pairs) > 0:
            self.parser.send_message(SamplerSample, ticks=self.ticks, var_size_pairs=var_size_pairs)
        self.eventloop.call_later(self.TICK_TIME, self.handle_time_event)


def ctypes_mem_from_size_and_val(val, size):
    if size == 4:
        return ctypes.c_int32(val)
    elif size == 2:
        return ctypes.c_int16(val)
    elif size == 1:
        return ctypes.c_int8(val)
    raise Exception("unknown size {}".format(size))


class SocketToFile(object):
    """
    Glue class to match a socket.socket to the file
    API used by Parser
    """
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
    """
    Glue class to match the expected eventloop API of FakeSineEmbedded
    and Client to the asyncio native library of python.
    """
    def __init__(self, loop):
        self.loop = loop

    def add_reader(self, fdlike, callback):
        if isinstance(fdlike, SocketToFile):
            fd = fdlike.socket
        else:
            fd = fdlike
        self.loop.add_reader(fd.fileno(), callback) # 'fileno()' is not needed for asyncio, but is for QEventLoop from quamash

    def call_later(self, dt, callback):
        self.loop.call_later(dt, callback)


async def make_serial_client(comport, baudrate, protocol):
    import serial_asyncio
    # TODO: test asyncserial also with the Protocol+Transport scheme.
    # But polling (pyserial-async latest) good enough I think, start with that
    ## import asyncserial
    ## return asyncserial.AsyncSerial(comport, baudrate=baudrate)
    serial, protocol = await serial_asyncio.create_serial_connection(asyncio.get_event_loop(),
                                                  protocol, comport, baudrate=baudrate, rtscts=True)
    client = await protocol.connection_made_future
    client.serial = serial # TODO - nicer way
    return client


async def get_serial_client(comport=None, hint_description=None, baudrate=1000000,
                            protocol=Client):
    import serial
    from serial.tools.list_ports import comports

    if comport is None:
        available = comports()
        if len(available) == 0:
            print("no com ports available - is board powered and connected?")
            raise SystemExit
        if hint_description is not None:
            hint_description = hint_description.lower()
            available = [x for x in available if hint_description in x.description.lower()]
        if len(available) == 0:
            print("no com port matching hint available - is board powered and connected?")
            raise SystemExit
        if len(available) > 1:
            print("picking the first out of available {}".format(','.join([x.device for x in available])))
        comport = available[0].device
    return await make_serial_client(comport, baudrate=baudrate, protocol=protocol)

