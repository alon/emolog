import struct
import sys
import argparse

import emolog


def decode_buf(buf):
    start = buf[:100]
    pos = 100
    while True:
        msg, rest, err = emolog.emo_decode(start)
        if len(rest) < 100:
            rest = rest + buf[pos:pos+100]
            pos += 100
        if pos % 10000000 == 0:
            print("{:2.2} {}/{}".format(float(pos) / len(buf), pos, len(buf)))
        if err and not isinstance(msg, emolog.SkipBytes):
            yield err, msg
        if pos + 100 > len(buf):
            break
        start = rest
    yield None, rest


def parse_pure(file):
    buf = open(file, 'rb').read()
    for f in decode_buf(buf):
        print(repr(f))


def decode_simple(buf):
    count = 0
    while True:
        count += 1
        msg, buf, err = emolog.emo_decode(buf)
        #print("{}: {}, {}".format(count, msg, err))
        if err and not isinstance(msg, emolog.SkipBytes):
            yield err, msg
        if len(buf) == 0 or isinstance(msg, emolog.MissingBytes):
            break
    yield None, buf


def parse_clock(file):
    buf = b''
    print(file)
    pos = 0
    with open(file, 'rb') as fd:
        while True:
            clock, len = struct.unpack('<fI', fd.read(8))
            pos += len
            print("{:8.04}: {:10} {:10}".format(clock, pos, len))
            buf = buf + fd.read(len)
            for err, msg in decode_simple(buf): # replace with decode_buf to get emolog.c:273 assertion
                if err is None:
                    break
                print("err, msg: {}, {}".format(err, msg))
            assert err is None
            buf = msg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=['pure', 'clock'], default='clock')
    parser.add_argument('--file', required=True)
    args = parser.parse_args()
    if args.mode == 'pure':
        parse_pure(args.file)
    else:
        parse_clock(args.file)


if __name__ == '__main__':
    main()