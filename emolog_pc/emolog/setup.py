from shutil import copy
from os import path, getcwd, chdir, system, stat
import sys

from .util import which


git_root_candidate = path.join('..', '.git')
if path.exists(git_root_candidate):
    GIT_ROOT = path.abspath('..')

module_dir = path.split(__file__)[0]

EMO_MESSAGE_TYPE_H_BASENAME = 'emo_message_t.h'

devel_protocol_lib_dir = path.abspath(path.join(module_dir, '..', '..', 'emolog_protocol', 'source'))

candidates = [path.join(d, EMO_MESSAGE_TYPE_H_BASENAME) for d in [module_dir, devel_protocol_lib_dir]]

EMO_MESSAGE_TYPE_H_FILENAME = None
for candidate in candidates:
    if path.exists(candidate):
        EMO_MESSAGE_TYPE_H_FILENAME = candidate

assert EMO_MESSAGE_TYPE_H_FILENAME, f"cannot find {EMO_MESSAGE_TYPE_H_BASENAME}"


def get_artifacts():
    """
    Builds or copies any file that isn't already in emolog directory into it,
    and returns a list of those files relative to the emolog directory.
    """
    assert path.exists(devel_protocol_lib_dir)
    ret = [path.join(devel_protocol_lib_dir, EMO_MESSAGE_TYPE_H_FILENAME)]
    assert all([path.exists(x) for x in ret]), "one of the artifacts doesn't exist"
    return ret

