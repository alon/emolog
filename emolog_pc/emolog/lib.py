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
    AckTimeout, VariableSampler, Parser,
    ClientBase)

if 'profile' not in builtins.__dict__:
    def nop_decorator(f):
        return f
    builtins.__dict__['profile'] = nop_decorator


logger = getLogger('emolog')


class Client(ClientBase):
    async def await_ack(self):
        await self.ack
        is_timeout = self.ack.result() == self.ACK_TIMEOUT
        self.reset_ack()
        if is_timeout:
            raise AckTimeout()

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
