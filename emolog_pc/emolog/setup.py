from shutil import copy
from os import path, getcwd, chdir, system, stat
import sys

from .util import which


if 'win' in sys.platform:
    LIB_RELATIVE_DIR = '../../emolog_protocol'
    LIB_FILENAME = 'emolog_protocol.dll'
    MAKE_EXEC = 'make.exe'
else:
    LIB_RELATIVE_DIR = '../../emolog_protocol'
    LIB_FILENAME = 'libemolog_protocol.so'
    MAKE_EXEC = 'make'
is_development_package = path.exists(path.join('..', '.git'))
module_dir = path.split(__file__)[0]

DEVEL_LIB_ABS_DIR = path.realpath(path.join(module_dir, LIB_RELATIVE_DIR))
DEVEL_PROTOCOL_LIB = path.join(DEVEL_LIB_ABS_DIR, LIB_FILENAME)
DEVEL_EMO_MESSAGE_TYPE_H_FILENAME = path.join(DEVEL_LIB_ABS_DIR, 'source/emo_message_t.h')

if is_development_package:
    LIB_ABS_DIR = DEVEL_LIB_ABS_DIR
    EMO_MESSAGE_TYPE_H_FILENAME = DEVEL_EMO_MESSAGE_TYPE_H_FILENAME
else:
    LIB_ABS_DIR = path.realpath(module_dir)
    EMO_MESSAGE_TYPE_H_FILENAME = path.join(LIB_ABS_DIR, 'emo_message_t.h')
PROTOCOL_LIB = path.join(LIB_ABS_DIR, LIB_FILENAME)


def build_protocol_library():
    # chdir to path of library
    orig_path = getcwd()
    if not path.exists(LIB_ABS_DIR):
        return # not actually a development checkout
    chdir(LIB_ABS_DIR)
    if not path.exists(LIB_FILENAME) or stat(LIB_FILENAME).st_mtime < stat('source/emolog_protocol.c').st_mtime:
        if which(MAKE_EXEC) is None:
            print("missing make; please place a copy of {} at {}".format(LIB_FILENAME, LIB_ABS_DIR))
            raise SystemExit
        ret = system("make {}".format(LIB_FILENAME))
        assert ret == 0, "make failed with error code {}, see above.".format(ret)
    assert path.exists(LIB_FILENAME)
    chdir(orig_path)
    return PROTOCOL_LIB


def build_artifacts():
    """
    Builds or copies any file that isn't already in emolog directory into it,
    and returns a list of those files relative to the emolog directory.
    """
    print(f"building {LIB_FILENAME}")
    protocol_lib_path = build_protocol_library()
    print(f"copying {LIB_FILENAME}")
    copy(protocol_lib_path, 'emolog')
    MESSAGE_TYPE_H_FILENAME = path.basename(DEVEL_EMO_MESSAGE_TYPE_H_FILENAME)
    print(f"copying {MESSAGE_TYPE_H_FILENAME}")
    copy(DEVEL_EMO_MESSAGE_TYPE_H_FILENAME, 'emolog')
    return [LIB_FILENAME, MESSAGE_TYPE_H_FILENAME]

