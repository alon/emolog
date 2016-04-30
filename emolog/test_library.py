import sys
import os
import ctypes


def test_decode_sane():



def run_tests():
    test_decode_sane()


def main():
    global lib
    lib = build_library()
    run_tests()


if __name__ == '__main__':
    main()
