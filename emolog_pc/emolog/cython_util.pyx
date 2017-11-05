from collections import defaultdict
from struct import unpack
from numpy import zeros, nan


def nans(l):
    a = zeros(l)
    a[:] = nan
    return a


def to_dicts(msgs):
    n = len(msgs)
    new_vals = defaultdict(lambda: nans(n))
    new_ticks = defaultdict(lambda: zeros(n))
    for i, (t, vpairs) in enumerate(msgs):
        for (name, val) in vpairs:
            new_vals[name][i] = val
            new_ticks[name][i] = t
    return new_ticks, new_vals


# cdef float _decode_little_endian_float(char *s):
#     return (float)*s


def decode_little_endian_float(s):
    # return _decode_little_endian_float(s)
    return unpack('<f', s)[0]