# cython: profile=False
# cython: linetrace=False

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

from array import array
import sys
from math import sin
from time import time
from logging import getLogger
from struct import pack, unpack
import csv

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


cdef extern from "emolog_protocol.h":
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

cdef unsigned calc_header_size():
    cdef bytes buf = b' ' * 100
    return emo_encode_ping(buf)

cdef unsigned HEADER_SIZE = calc_header_size()

def header_size():
    return HEADER_SIZE


MAGIC = unpack(ENDIANESS + 'H', b'EM')[0]

### Messages


cdef class Message:
    # Used by all encode functions - can segfault if buffer is too small
    buf = b'\x00' * 1024  # create_string_buffer(buf_size)
    cdef public unsigned seq

    def __init__(self, seq):
        self.seq = seq

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


cdef class Version(Message):
    type = emo_message_types.version
    cdef unsigned version
    cdef unsigned reply_to_seq
    def __init__(self, unsigned seq, unsigned version=0, unsigned reply_to_seq=0):
        self.seq = seq
        self.version = version
        self.reply_to_seq = reply_to_seq

    def encode_inner(self):
        return emo_encode_version(self.buf, self.reply_to_seq if self.reply_to_seq is not None else self.seq)

    def handle_by(self, handler):
        #logger.debug(f"Got Version: {self.version}")
        handler.ack_received()


class Ping(Message):
    type = emo_message_types.ping
    def encode_inner(self):
        return emo_encode_ping(self.buf)


class Ack(Message):
    type = emo_message_types.ack
    def __init__(self, seq, error, reply_to_seq):
        self.seq = seq
        self.error = error
        self.reply_to_seq = reply_to_seq

    def encode_inner(self):
        return emo_encode_ack(self.buf, self.reply_to_seq, self.error)

    def handle_by(self, handler):
        #print("Ack.handle_by")
        if self.error != 0:
            logger.error(f"embedded responded to {self.reply_to_seq} with ERROR: {self.error}")
        handler.ack_received()

    def __str__(self):
        # TODO - string for error
        return '<{} {} {}>'.format('ack' if self.error == 0 else 'nack', self.reply_to_seq, self.error)

    __repr__ = __str__


cdef class SamplerRegisterVariable(Message):
    type = emo_message_types.sampler_register_variable
    cdef public unsigned phase_ticks
    cdef public unsigned period_ticks
    cdef public unsigned address
    cdef public unsigned size

    def __init__(self, unsigned seq, unsigned phase_ticks, unsigned period_ticks, unsigned address, unsigned size):
        self.seq = seq
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

cdef class SamplerClear(Message):
    type = emo_message_types.sampler_clear

    def encode_inner(self):
        return emo_encode_sampler_clear(self.buf)


cdef class SamplerStart(Message):
    type = emo_message_types.sampler_start

    def encode_inner(self):
        return emo_encode_sampler_start(self.buf)


cdef class SamplerStop(Message):
    type = emo_message_types.sampler_stop

    def encode_inner(self):
        return emo_encode_sampler_stop(self.buf)



cdef class SamplerSample(Message):
    type = emo_message_types.sampler_sample
    cdef public unsigned ticks
    cdef public bytes payload
    cdef public list var_size_pairs

    def __init__(self, unsigned seq, unsigned ticks, bytes payload=None, list var_size_pairs=None):
        """
        :param ticks:
        :param vars: dictionary from variable index to value
        :return:
        """
        if var_size_pairs is None:
            var_size_pairs = []
        self.seq = seq
        self.ticks = ticks
        self.payload = payload
        self.var_size_pairs = var_size_pairs

    def encode_inner(self):
        emo_encode_sampler_sample_start(self.buf)
        for var, size in self.var_size_pairs:
            emo_encode_sampler_sample_add_var(self.buf, to_str(var, size), size)
        return emo_encode_sampler_sample_end(self.buf, self.ticks)

    def handle_by(self, handler):
        if handler.sampler.running:
            handler.pending_samples.append((self.seq, self.ticks, self.payload))
            #logger.debug(f"Got Sample: {self}")
        else:
            #logger.debug("ignoring sample since PC sampler is not primed")
            pass

    cdef update_with_sampler(self, VariableSampler sampler):
        self.variables = sampler.variables_from_ticks_and_payload(ticks=self.ticks, payload=self.payload)

    @classmethod
    def empty_size(cls):
        sample = cls(seq=0, ticks=0)
        return sample.encode_inner()

    def __str__(self):
        if self.var_size_pairs is not None:
            assert self.payload is None
            return '<sample {} var_size_pairs {}>'.format(self.ticks, self.var_size_pairs)
        elif self.payload is not None:
            return '<sample {} undecoded {}>'.format(self.ticks, repr(self.payload))
        else:
            return '<sample {} error>'.format(self.ticks)

    __repr__ = __str__


class MissingBytes:
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


class SkipBytes:
    def __init__(self, skip):
        self.skip = skip

    def __str__(self):
        return "Skip Bytes {}".format(self.skip)

    def handle_by(self, handler):
        pass

    __repr__ = __str__


class UnknownMessage:
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


cdef (unsigned, unsigned, unsigned) decode_emo_header_unsafe(s):
    """
    Decode emolog header assuming the MAGIC is correct
    :param s: bytes of header
    :return: success (None if yes, string of error otherwise), message type (byte), payload length (uint16), message sequence (byte)
    """
    cdef unsigned _magic
    cdef unsigned _type
    cdef unsigned length
    cdef unsigned payload_crc
    cdef unsigned header_crc
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


cdef class RegisteredVariable:
    cdef public str name
    cdef public int phase_ticks
    cdef public int period_ticks
    cdef public unsigned address
    cdef public unsigned size
    cdef public object _type
    def __init__(self, name, phase_ticks, period_ticks, address, size, _type):
        self.name = name
        self.phase_ticks = phase_ticks
        self.period_ticks = period_ticks
        self.address = address
        self.size = size
        self._type = _type


@cython.final
cdef class VariableSampler:
    # variables
    cdef list name
    cdef int[:] phase_ticks
    cdef int[:] period_ticks
    cdef unsigned[:] address
    cdef unsigned[:] size
    cdef list _type
    cdef bint _use_unpack
    cdef bint _single_sample
    cdef bytes _single_sample_unpack_str

    cdef public bint running

    def __init__(self):
        self._set_variables([])
        self.running = False

    def clear(self):
        self._set_variables([])

    def on_started(self):
        self.running = True

    def on_stopped(self):
        self.running = False

    def register_variables(self, variables):
        out = []
        for d in variables:
            name, phase_ticks, period_ticks, address, size, _type = (
                d['name'], d['phase_ticks'], d['period_ticks'], d['address'], d['size'], d['_type']
            )
            out.append(RegisteredVariable(
                name=name,
                phase_ticks=phase_ticks,
                period_ticks=period_ticks,
                address=address,
                size=size,
                _type=_type))
        self._set_variables(out)

    cdef _set_variables(self, variables):
        self.name = [x.name for x in variables]
        self.phase_ticks = array('i', [x.phase_ticks for x in variables])
        self.period_ticks = array('i', [x.period_ticks for x in variables])
        self.address = array('I', [x.address for x in variables])
        self.size = array('I', [x.size for x in variables])
        self._type = [x._type for x in variables]
        # special case really fast - all variables has zero phase and same period
        self._use_unpack = not any(hasattr(t, 'decode') for t in self._type) # conservative
        if len(variables) == 0:
            self._use_unpack = self._single_sample = False
            return
        if not self._use_unpack:
            print(f"sample decoding mode: mixed unpack and decoder")
            self._single_sample = False
        else:
            self._single_sample = all(x == 0 for x in self.phase_ticks) and all (x == 1 for x in self.period_ticks)
            if len(variables) > 0 and self._single_sample:
                print("sample decoding mode: single unpack")
                self._single_sample_unpack_str = b'<' + b''.join(t.unpack_str for t in self._type)
            else:
                print("sample decoding mode: multiple unpack")

    cdef list_from_ticks_and_payload(self, dict name_to_index, int ticks, bytes payload):
        cdef unsigned offset = 0
        cdef unsigned size
        cdef unsigned i
        if self._single_sample:
            values = list(unpack(self._single_sample_unpack_str, payload))
            types = self._type
        else:
            types_enum = [(self._type[i], i) for i in range(self.phase_ticks.size)
                        if ticks % self.period_ticks[i] == self.phase_ticks[i]]
            values = [None] * len(self.name)
            types = [None] * len(self.name)
            if self._use_unpack:
                unpacked = list(unpack(b'<' + b''.join(t.unpack_str for t, i in types_enum), payload))
                for (t, i), v in zip(types_enum, unpacked):
                    values[i] = v
                    types[i] = t
            else:
                for t, i in types_enum:
                    size = self.size[i]
                    encoded = payload[offset:offset + size]
                    if hasattr(t, 'decode'):
                        val = t.decode(encoded)
                    else:
                        val, = unpack(b'<' + t.unpack_str, encoded)
                    try:
                        ind = name_to_index[self.name[i]]
                        values[ind] = val
                        types[ind] = t
                    except:
                        try:
                            print(f'{i}')
                            print(f'{self.name[i]}')
                            print(f'{name_to_index[self.name[i]]}')
                        finally:
                            raise SystemExit
                    offset += size
                if offset != len(payload):
                    print(f"payload {len(payload)} but only unpacked {offset}")
        return types, values


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


cpdef emo_decode(bytes buf, unsigned i_start):
    cdef unsigned n = len(buf)
    cdef object error = None
    cdef unsigned payload_start
    cdef bytes header # make not a copy
    cdef bytes payload # make not a copy
    cdef unsigned emo_type
    cdef unsigned emo_len
    cdef unsigned seq
    cdef int needed = emo_decode_with_offset(buf, i_start, min(n - i_start, 0xffff))

    if needed == 0:
        payload_start = i_start + HEADER_SIZE
        header = buf[i_start : payload_start]
        emo_type, emo_len, seq = decode_emo_header_unsafe(header)
        i_next = payload_start + emo_len
        payload = buf[payload_start : i_next]
        if emo_type == emo_message_types.sampler_sample:
            # TODO: this requires having a variable map so we can compute the variables from ticks
            ticks = unpack(SAMPLER_SAMPLE_TICKS_FORMAT, payload[:4])[0]
            msg = SamplerSample(seq=seq, ticks=ticks, payload=payload[4:])
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
        error = 'missing bytes'
    else:
        msg = SkipBytes(-needed)
        i_next = i_start - needed
        error = 'skip bytes'
    return msg, i_next, error


cdef class Parser:
    cdef unsigned send_seq
    cdef unsigned empty_count
    cdef bytes buf
    cdef public object transport
    cdef bint debug_message_encoding
    cdef bint debug_message_decoding

    def __init__(self, transport, bint debug=False):
        self.transport = transport
        self.buf = b''
        self.send_seq = 0
        self.empty_count = 0

        # debug flags
        self.debug_message_encoding = debug
        self.debug_message_decoding = debug

    cpdef consume_and_return_messages(self, bytes s):
        if len(s) == 0:
            self.empty_count += 1
            # stream closed - quit - but wait a bit to be sure
            if self.empty_count > 2:
                print("DEBUG - SHOULD WE SYSTEM EXIT HERE?")
                raise SystemExit()
        self.buf = self.buf + s
        cdef unsigned i = 0
        cdef unsigned i_next
        cdef bytes buf = self.buf
        cdef unsigned n = len(buf)
        cdef list ret = []
        while i < n:
            msg, i_next, error = emo_decode(buf, i_start=i)
            if error:
                if isinstance(msg, SkipBytes):
                    parsed_buf = buf[i:i_next]
                    logger.debug("communication error - skipped {} bytes: {}".format(msg.skip, parsed_buf))
                elif isinstance(msg, MissingBytes):
                    break
                else:
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
            ret.append(msg)
            i = i_next
        self.buf = self.buf[i:]
        if len(self.buf) > 1024:
            print("WARNING: something is wrong with the packet decoding: {} bytes left (from {})".format(
                len(self.buf), len(self.buf) + i))
        return ret

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

##### Client

class Dumper:
    def write(self, b):
        sys.stdout.write(repr(b))

dumper = Dumper()


##### CSVHandler

# TODO, with np.ndarray[DTYPE_t, ndim=2]
#ctypedef np.bytes_t DTYPE_t

cdef object encode_if_bytes(object b):
    if isinstance(b, bytes):
        return b.encode('utf-8')
    return b


def default_csv_factory(filename, fields, *args, **kw):
    """
    fields - unused by the default factory.
    """
    fd = open(filename, 'w+')
    return csv.writer(fd, *args, **kw)


cdef class CSVHandler:
    cdef bint _running
    cdef bint verbose
    cdef bint dump
    cdef long first_ticks
    cdef long last_ticks
    cdef long min_ticks
    cdef list names
    cdef set sample_listeners
    cdef list data # (np.ndarray not good enough for array types ; can specialize (fast use case doesn't have arrays)) to be made into an array
    cdef dict name_to_index
    cdef VariableSampler sampler
    cdef bint write_immediately # for testing - should commit
    cdef object writer

    cdef public str csv_filename
    cdef public object csv_writer_factory
    cdef public list csv_fields
    cdef public long max_ticks
    cdef public long ticks_lost
    cdef public long samples_received

    def __init__(self, sampler, verbose, dump, csv_writer_factory):
        self.sampler = sampler
        self.verbose = verbose
        self.dump = dump
        self.csv_filename = None
        self.first_ticks = -1
        self.last_ticks = -1
        self.min_ticks = 0
        self.names = []
        self.samples_received = 0
        self.ticks_lost = 0
        self.max_ticks = 0
        self._running = False
        self.sample_listeners = set()
        self.write_immediately = True
        if csv_writer_factory is None:
            csv_writer_factory = default_csv_factory
        self.csv_writer_factory = csv_writer_factory

    def reset(self, str csv_filename, list names, long min_ticks, long max_ticks):
        assert max_ticks > 0, "max_ticks must be none zero, used as stopping condition for saving CSV"
        if self._running:
            self._save_csv()
        self.csv_filename = csv_filename
        self.first_ticks = -1
        self.last_ticks = -1
        self.min_ticks = min_ticks
        self.names = names
        self.csv_fields = ['sequence', 'ticks', 'timestamp'] + self.names
        self.name_to_index = {name: i for i, name in enumerate(names)}
        self.samples_received = 0
        self.ticks_lost = 0
        self.max_ticks = max_ticks
        self._running = True
        if not self.write_immediately:
            N_cols = 3 + len(self.names)
            data = [[None] * N_cols for i in range(max_ticks)] # TODO: 64 bytes per entry - so for 20 seconds, 10 variables, 20e3/sec ~ 120 MiB
            #self.data = np.array(data, dtype='string_').reshape(max_ticks, N_cols)
            self.data = data
        else:
            self.writer = self._init_csv()

    def register_listener(self, callback):
        self.sample_listeners.add(callback)

    cpdef bint running(self):
        return self._running

    cpdef long total_ticks(self):
        if self.first_ticks == -1 or self.last_ticks == -1:
            return 0
        return self.last_ticks - self.first_ticks

    def stop(self):
        if not self._running:
            return
        self._running = False
        self._save_csv()

    def _save_csv(self):
        if self.write_immediately:
            return
        writer = self._init_csv()
        for i, row in enumerate(self.data):
            writer.writerow(row[:3] + [encode_if_bytes(t.to_csv_val(v)) for t, v in zip(self.sampler._type, row[3:])])

    cdef _init_csv(self):
        if self.csv_filename is None:
            return
        writer = self.csv_writer_factory(self.csv_filename, fields=self.csv_fields, lineterminator='\n')
        writer.writerow(self.csv_fields)
        return writer

    # python version for profiling
    cpdef handle_sampler_samples(self, msgs):
        """
        Write to CSV, add points to plots
        :param msgs: [(seq, ticks, {name: value})]
        :return: None
        """
        cdef list data
        cdef list new_float_only_msgs
        cdef int missing
        cdef float now
        cdef bint have_listeners

        if not self._running:
            return
        # cdef np.ndarray[np.double_t, ndim = 2]
        data = self.data
        # prune messages if we got too many
        missing = self.max_ticks - self.samples_received
        if len(msgs) > missing:
            del msgs[missing:]
        # TODO - decode variables (integer/float) in emolog VariableSampler
        now = time() * 1000
        have_listeners = len(self.sample_listeners) > 0
        if have_listeners:
            new_float_only_msgs = []
        name_to_index = self.name_to_index
        for seq, ticks, payload in msgs:
            types, values = self.sampler.list_from_ticks_and_payload(name_to_index=name_to_index, ticks=ticks, payload=payload)
            row_start = [seq, ticks, now]
            if self.write_immediately:
                self.writer.writerow(row_start + [(encode_if_bytes(t.to_csv_val(v)) if v is not None else None) for t, v in zip(types, values)])
            elif 0 <= ticks < len(self.data):
                data[ticks] = row_start + values
                if have_listeners:
                    new_float_only_msgs.append((ticks, [(self.names[i], v) for i, v in enumerate(values) if v is not None and type(v) == float]))
            else:
                print(f"error {ticks} > {len(self.data)} or {ticks} < 1")
            if self.first_ticks == -1:
                self.first_ticks = ticks
            if self.last_ticks != -1 and ticks - self.last_ticks != self.min_ticks:
                print("{:8.5}: ticks jump {:6} -> {:6} [{:6}]".format(
                    now / 1000, self.last_ticks, ticks, ticks - self.last_ticks))
                self.ticks_lost += ticks - self.last_ticks - self.min_ticks
            self.last_ticks = ticks
        if have_listeners:
            for listener in self.sample_listeners:
                listener(new_float_only_msgs)
        self.samples_received += len(msgs)
        if self.max_ticks != 0 and self.total_ticks() + 1 >= self.max_ticks:
            self.stop()

#####

cdef class EmotoolCylib:
    """
    """

    cdef bint dump
    cdef bint verbose
    cdef int _received_samples
    cdef object dump_out
    cdef object parent
    cdef public VariableSampler sampler
    cdef public list pending_samples
    cdef public Parser parser
    cdef public CSVHandler csv_handler

    def __init__(self, parent, verbose=False, dump=None, csv_writer_factory=None):
        self.parent = parent
        self.verbose = verbose
        self.dump = dump is not None and dump is not False
        if dump:
            self.dump_out = open(dump, 'wb')
        self.sampler = VariableSampler()
        self._received_samples = 0
        self.pending_samples = []
        self.parser = Parser(None, debug=self.verbose)
        self.csv_handler = CSVHandler(sampler=self.sampler, verbose=verbose, dump=dump,
                                      csv_writer_factory=csv_writer_factory)

    @property
    def received_samples(self):
        return self._received_samples

    def dump_buf(self, buf):
        self.dump_out.write(pack('<fI', time(), len(buf)) + buf)
        #self.dump.flush()

    def _debug_log(self, s):
        logger.debug(s)

    def data_received(self, bytes data):
        if self.dump:
            self.dump_buf(data)
        for msg in self.parser.consume_and_return_messages(data):
            msg.handle_by(self)
        if len(self.pending_samples) > 0:
            self.csv_handler.handle_sampler_samples(self.pending_samples)
            self._received_samples += len(self.pending_samples)
            del self.pending_samples[:]

    def ack_received(self):
        self.parent.set_future_result(self.parent.ack, True)

    def running(self):
        return self.csv_handler.running()
