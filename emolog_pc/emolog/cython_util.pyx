from collections import defaultdict
from struct import unpack
from functools import wraps
from time import time

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


def coalesce_meth(hertz):
    """
    decorator to call real function.
    TODO: use callback mechanism, since otherwise this ends up possibly forgetting
    the last point. Since we intend to work at 20000 Hz and look at seconds, this is
    not a real problem
    """
    dt = 1.0 / hertz
    def wrappee(f):
        last_time = [None]
        total_msgs = []
        @wraps(f)
        def wrapper(self, msgs):
            total_msgs.extend(msgs)
            cur_time = time()
            lt = last_time[0]
            if lt is None or cur_time - lt >= dt:
                last_time[0] = cur_time
            else:
                return
            f(self, total_msgs)
            total_msgs.clear()
        return wrapper
    return wrappee
