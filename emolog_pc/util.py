import subprocess
import os
from time import time
from functools import wraps


def which(filename):
    path = os.environ.get('PATH', '.').split(os.pathsep)
    for d in path:
        if os.path.exists(os.path.join(d, filename)):
            return os.path.join(d, filename)
    return None


def version():
    """
    get git defined version. later: return version of program encoded in a install
    produced variable.
    :return:
    """
    gitroot = os.path.realpath(os.path.join(os.path.split(__file__)[0], '..', '.git'))
    if not os.path.exists(gitroot):
        return "unknown version"
    try:
        orig_path = os.getcwd()
        os.chdir(gitroot)
        output = subprocess.check_output("git describe --tags".split()).strip()
    except:
        return "unknown version"
    finally:
        os.chdir(orig_path)
    return output.strip().decode('utf-8')


def coalesce_meth(hertz):
    """ decorator to call real function.
    TODO: use async loop mechanism, since otherwise this ends up possibly forgetting
    the last point. Since we intend to work at 20000 Hz and look at seconds, this is
     not a real problem"""
    dt = 1.0 / hertz
    def wrappee(f):
        last_time = [None]
        msgs = []
        @wraps(f)
        def wrapper(self, msg):
            msgs.append(msg)
            cur_time = time()
            if last_time[0] is None or cur_time - last_time[0] >= dt:
                last_time[0] = cur_time
            else:
                return
            f(self, msgs)
            msgs.clear()
        return wrapper
    return wrappee
