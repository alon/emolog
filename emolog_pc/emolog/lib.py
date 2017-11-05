# instead of __all__ just only import what we care about

# from .cylib import (
# decode_emo_header_unsafe,
# Client,
# Parser,
# FakeSineEmbedded,
# Version,
# Ack,
# AckTimeout,
# Ping,
# SamplerSample,
# SamplerRegisterVariable,
# SamplerClear,
# SamplerStart,
# SamplerStop,
# build_protocol_library,
# )

from asyncio import Future, Protocol, sleep, get_event_loop
from asyncio.futures import InvalidStateError
from collections import namedtuple
from time import time
from struct import pack
import sys
from math import sin
from logging import getLogger

import builtins # profile will be here when run via kernprof

from .cylib import (
    SamplerRegisterVariable, SamplerClear, SamplerSample, SamplerStart, SamplerStop, Ack, Version,
    Message,
    AckTimeout, VariableSampler, Parser)

if 'profile' not in builtins.__dict__:
    def nop_decorator(f):
        return f
    builtins.__dict__['profile'] = nop_decorator


logger = getLogger('emolog')



### Code depending on lib


class Dumper:
    def write(self, b):
        sys.stdout.write(repr(b))

dumper = Dumper()


class Client(Protocol):
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
        self.dump.write(pack('<fI', time(), len(buf)) + buf)
        #self.dump.flush()

    def exit_gracefully(self):
        self.stopped = True
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
        msgs = self.parser.iter_available_messages(data)
        for msg in msgs:
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


class FakeSineEmbedded(Protocol):
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
        self.tick_time = 1.0 / (ticks_per_second if ticks_per_second > 0 else 20000)
        self.verbose = True
        self.parser = None
        self.sines = []
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
        dt = max(0.0, self.tick_time * self.ticks + self.start_time - time()) if self.ticks_per_second > 0.0 else 0
        self.eventloop.call_later(dt, self.handle_time_event)
