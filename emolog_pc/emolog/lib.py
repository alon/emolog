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
    SamplerRegisterVariable, SamplerSample, SamplerClear, SamplerStart, SamplerStop,
    VariableSampler, Parser, EmotoolCylib, CSVHandler,
    Version, Ping,
    Message, Ack, SamplerSample,
    header_size, emo_decode
    )

if 'profile' not in builtins.__dict__:
    def nop_decorator(f):
        return f
    builtins.__dict__['profile'] = nop_decorator


logger = getLogger('emolog')


class Futures:
    CHECK_DT = 0.1
    def __init__(self):
        self._futures = {}
        self._new_futures = {}
        get_event_loop().create_task(self.reaper())

    async def reaper(self):
        while True:
            await sleep(self.CHECK_DT)
            now = time()
            removed = []
            for f, (start_time, timeout, timeout_result) in self._futures.items():
                if f.done():
                    removed.append(f)
                elif timeout is not None and now > start_time + timeout:
                    self.set_future_result(f, timeout_result)
                    removed.append(f)
            for f in removed:
                if f in self._futures:
                    del self._futures[f]
            self._futures.update(self._new_futures)
            self._new_futures.clear()

    def cancel_all(self):
        for f, (start_time, timeout, timeout_result) in self._futures.items():
            f.cancel()
        self._futures.clear()

    def add_future(self, timeout=None, timeout_result=None):
        f = Future()
        self._new_futures[f] = (time(), timeout, timeout_result)
        return f

    def set_future_result(self, future, result):
        try:
            future.set_result(result)
        except InvalidStateError:
            pass # silently swallow error, means a double set_result


def test_futures():
    el = get_event_loop()
    futures = Futures()
    f1 = futures.add_future(timeout=3.0, timeout_result='Busted')
    f2 = futures.add_future(timeout=0.1, timeout_result='Busted')
    async def dosleep():
        while not f1.done() or not f2.done():
            await sleep(0.5)
            if not f1.done():
                f1.set_result(None)
    get_event_loop().run_until_complete(dosleep())
    print(f1.result())
    print(f2.result())


class AckTimeout(Exception):
    pass


class ClientProtocolMixin(Protocol):
    """
    To use, inherit also from CyClientBase
    You cannot inherit from it here to avoid two classes with predefined structure
    inheriting and resulting in an error
    """
    ACK_TIMEOUT_SECONDS = 40.0
    ACK_TIMEOUT = 'ACK_TIMEOUT'

    def __init__(self, verbose, dump, csv_writer_factory=None):
        Protocol.__init__(self)
        self.cylib = EmotoolCylib(
            parent=self, verbose=verbose, dump=dump,
            csv_writer_factory=csv_writer_factory)
        self.futures = Futures()
        self.reset_ack()
        self.connection_made_future = self.futures.add_future()

    def set_future_result(self, future, result):
        self.futures.set_future_result(future, result)

    def connection_made(self, transport):
        self.transport = transport
        self.cylib.parser.set_transport(transport)
        self.set_future_result(self.connection_made_future, self)

    def connection_lost(self, exc):
        # generally, what do we want to do at this point? it could mean USB was unplugged, actually has to be? if client stops
        # this wouldn't happen - we wouldn't notice at this level. So quit?
        #self._debug_log("serial connection_lost")
        pass

    def exit_gracefully(self):
        self.futures.cancel_all()

    def send_message(self, msg_type, **kw):
        self.cylib.parser.send_message(msg_type, **kw)
        self.ack = self.futures.add_future(timeout=self.ACK_TIMEOUT_SECONDS, timeout_result=self.ACK_TIMEOUT)

    def reset_ack(self):
        self.ack = Future()
        self.ack.set_result(True)

    async def await_ack(self):
        try:
            await self.ack
        except Exception as e:
            import pdb; pdb.set_trace()
        # XXX sometimes result is not available. Probably as a result of an ack
        # being set to a new one. Treat it as no timeout.
        try:
            result = self.ack.result()
        except:
            result = None
        is_timeout = result == self.ACK_TIMEOUT
        self.reset_ack()
        if is_timeout:
            print(f"{self.futures._futures!r}")
            raise AckTimeout()

    async def send_set_variables(self, variables):
        await self.send_sampler_clear()
        self.cylib.sampler.clear()
        for d in variables:
            await self.send_sampler_register_variable(
                phase_ticks=d['phase_ticks'],
                period_ticks=d['period_ticks'],
                address=d['address'],
                size=d['size']
            )
        self.cylib.sampler.register_variables(variables)

    async def send_sampler_clear(self):
        await self.send_and_ack(SamplerClear)

    async def send_sampler_register_variable(self, phase_ticks, period_ticks, address, size):
        await self.send_and_ack(SamplerRegisterVariable,
            phase_ticks=phase_ticks, period_ticks=period_ticks, address=address, size=size)

    async def send_sampler_clear(self):
        await self.send_and_ack(SamplerClear)

    async def send_sampler_start(self):
        await self.send_and_ack(SamplerStart)
        self.cylib.sampler.on_started()

    async def send_sampler_stop(self):
        await self.send_and_ack(SamplerStop)
        self.cylib.sampler.on_stopped()

    async def send_version(self):
        # We don't tell our version to the embedded right now - it doesn't care
        # anyway
        await self.send_after_last(Version)

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
