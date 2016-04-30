import ctypes
import struct

from serial import Serial

from emolog import emolog


lib = emolog()


def dump_crctable():
    with open('crcdump.pickle', 'wb') as fd:
        fd.write(lib.crcTable, 256)


WPP_MESSAGE_TYPE_VERSION = 1

header_size = 10

def decode_wpp_header(s):
    assert len(s) >= header_size
    m1, m2, m3, t, l, seq, payload_crc, header_crc = struct.unpack('<BBBBHHBB', s[:header_size])
    if [m1, m2, m3] != map(ord, 'CMP'):
        print("bad magic: {}, {}, {}".format(m1, m2, m3))
        return False, None, None
    print("got message: type {}, seq {}, length {}".format(t, seq, l))
    return True, t, l


buf_size = 1024
buf = ctypes.create_string_buffer(buf_size)
def write_version(s):
    buf_filled = lib.wpp_encode_version(buf, -1)
    print("writing {} bytes: {}".format(buf_filled, repr(buf[:buf_filled])))
    s.write(buf[:buf_filled])


def main():
    print("library seq: {}".format(lib.get_seq()))
    s = Serial('/dev/ttyACM0', baudrate=115200)
    buf_in = ''
    success = 0
    write_version(s)
    while success < 2:
        buf_in += s.read()
        needed = lib.wpp_decode(buf_in, len(buf_in))
        if needed == 0:
            valid, wpp_type, wpp_len = decode_wpp_header(buf_in)
            if wpp_type == WPP_MESSAGE_TYPE_VERSION:
                (client_version,) = struct.unpack('<L', buf_in[10:14])
                print("got version message from client. version = {}".format(client_version))
                success += 1
                if success < 2:
                    write_version(s)
                buf_in = ''
        if needed == -1:
            print("got: {}: {}".format(len(buf_in), repr(buf_in)))
            raise SystemExit



if __name__ == '__main__':
    main()
