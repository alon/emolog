"""
Wrap emolog c library. Build it if it doesn't exist. Provides the same
API otherwise, plus helpers.
"""

import ctypes
import os
import struct
import sys


__all__ = ['WPP_MESSAGE_TYPE_VERSION',
           'decode_emo_header',
           'encode_version',
           'write_version']



if 'win' in sys.platform:
    LIBRARY_PATH = 'emolog.dll'
else:
    LIBRARY_PATH = 'libemolog.so'


def build_library():
    # chdir to path of module
    os.chdir(os.path.split(__file__)[0])
    os.system("make {}".format(LIBRARY_PATH))
    assert os.path.exists(LIBRARY_PATH)


def emolog():
    if not os.path.exists(LIBRARY_PATH):
        build_library()
    assert os.path.exists(LIBRARY_PATH)
    lib = ctypes.CDLL(LIBRARY_PATH)
    return lib


# importing builds!
lib = emolog()


### Globals

WPP_MESSAGE_TYPE_VERSION = 1
header_size = 10

MAGIC_VALUES = list(map(ord, 'CMP'))

### Messages


class Message(object):
    pass


class Version(Message):
    def __init__(self, version):
        self.version = version


class MissingBytes(object):
    def __init__(self, needed):
        self.needed = needed


class SkipBytes(object):
    def __init__(self, skip):
        self.skip = skip


### Code depending on lib

def dump_crctable():
    with open('crcdump.pickle', 'wb') as fd:
        fd.write(lib.crcTable, 256)


def get_seq():
    return lib.get_seq()


def decode_emo_header(s):
    """

    :param s: bytes of header
    :return: success (bool), message type (byte), payload length (uint16)
    """
    assert len(s) >= header_size
    m1, m2, m3, t, l, seq, payload_crc, header_crc = struct.unpack('<BBBBHHBB', s[:header_size])
    if [m1, m2, m3] != MAGIC_VALUES:
        print("bad magic: {}, {}, {} (expected {}, {}, {})".format(m1, m2, m3, *MAGIC_VALUES))
        return False, None, None
    print("got message: type {}, seq {}, length {}".format(t, seq, l))
    return True, t, l


class ClientParser(object):
    def __init__(self):
        self.buf = b''

    def incoming(self, s):
        assert isinstance(s, bytes)
        self.buf = self.buf + s
        needed = lib.emo_decode(self.buf, len(self.buf))
        msg = None
        if needed == 0:
            valid, emo_type, emo_len = decode_emo_header(self.buf)
            if emo_type == WPP_MESSAGE_TYPE_VERSION:
                (client_version,) = struct.unpack('<L', self.buf[10:14])
                msg = Version(client_version)
                self.buf = b''
        elif needed > 0:
            msg = MissingBytes(needed)
        else:
            msg = SkipBytes(-needed)
        return msg

    def __str__(self):
        return '<ClientParser: #{}: {!r}'.format(len(self.buf), self.buf)

    __repr__ = __str__


buf_size = 1024
buf = ctypes.create_string_buffer(buf_size)
def encode_version():
    buf_filled = lib.emo_encode_version(buf, -1)
    print("writing {} bytes: {}".format(buf_filled, repr(buf[:buf_filled])))
    return buf[:buf_filled]


# Helpers to write messages to a file like object, like serial.Serial

def write_version(s):
    s.write(encode_version())
