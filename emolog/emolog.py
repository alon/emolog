"""
Wrap emolog c library. Build it if it doesn't exist. Provides the same
API otherwise, plus helpers.
"""

import ctypes
import os


__all__ = ['emolog']


LIBRARY_PATH = './libcmwpp.so'


lib = None



def build_library():
    os.system("make {}".format(LIBRARY_PATH))
    assert os.path.exists(LIBRARY_PATH)


def emolog():
    if not os.path.exists(LIBRARY_PATH):
        build_library()
    lib = ctypes.CDLL(LIBRARY_PATH)
    return lib
