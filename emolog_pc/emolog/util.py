import subprocess
import os
from importlib import import_module


# for kernprof
import builtins
if 'profile' not in builtins.__dict__:
    builtins.__dict__['profile'] = lambda x: x


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
    gitroot = os.path.realpath(os.path.join(os.path.split(__file__)[0], '..', '..', '.git'))
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


def resolve(module_attr):
    """
    resolve the given string such that it is equivalent to doing
    from module_attr::all_but_last import module_attr::last

    i.e. a.b.c would be
    from a.b import c
    """
    try:
        module, attr = module_attr.rsplit('.', 1)
        return getattr(import_module(module), attr)
    except:
        return None
