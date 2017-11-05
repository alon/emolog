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
from time import time
from struct import pack
import sys
from logging import getLogger

import builtins # profile will be here when run via kernprof

from .cylib import (
    SamplerRegisterVariable, SamplerSample, SamplerClear, SamplerStart, SamplerStop, Version,
    FakeSineEmbedded,
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

