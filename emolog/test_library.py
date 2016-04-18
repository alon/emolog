import sys
import os
import ctypes


LIBRARY_PATH = 'libcmwpp.so'

def build_library():
    os.system("make {}".format(LIBRARY_PATH))
    assert os.path.exists('
    lib = ctypes.CDLL(LIBRARY_PATH)
    return lib


def test_decode_sane():



def run_tests():
    test_decode_sane()


def main():
    global lib
    lib = build_library()
    run_tests()


if __name__ == '__main__':
    main()
