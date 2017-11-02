from shutil import copy
from os import path

from .lib import build_protocol_library, LIB_FILENAME, DEVEL_EMO_MESSAGE_TYPE_H_FILENAME


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

