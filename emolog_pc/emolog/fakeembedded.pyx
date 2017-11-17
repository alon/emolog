#### FakeEmbedded

from time import time
from math import sin
from asyncio import Protocol, get_event_loop
from .lib import Message, Parser, SamplerClear, SamplerStart, SamplerStop, SamplerRegisterVariable, Version, Ack, SamplerSample


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
    cdef int sines_num
    cdef int start_time
    cdef bint running
    cdef int ticks
    cdef object eventloop
    cdef bint verbose
    cdef object parser # TODO - how to specify this is Parser extension type - resides in cylib.pyx

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
        for msg in self.parser.consume_and_return_messages(data):
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

