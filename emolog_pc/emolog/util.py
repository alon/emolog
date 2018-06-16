from subprocess import check_output, Popen
import os
from importlib import import_module
from psutil import Process, NoSuchProcess, wait_procs, TimeoutExpired


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
        output = check_output("git describe --tags".split()).strip()
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


processes = []


def create_process(cmdline):
    print("starting subprocess: {}".format(cmdline))
    process = Popen(cmdline)
    processes.append(process)
    return process


def kill_all_processes():
    for process in processes:
        #print("killing {}".format(process.pid}))
        if hasattr(process, 'send_ctrl_c'):
            process.send_ctrl_c()
        else:
            kill_proc_tree(process.pid)
    del processes[:]


def kill_proc_tree(pid, including_parent=True, timeout=5):
    try:
        parent = Process(pid)
    except NoSuchProcess:
        return
    children = parent.children(recursive=True)
    for child in children:
        if verbose.kill:
            print("killing {}".format(child.pid))
        try:
            child.kill()
            child.terminate()
        except NoSuchProcess:
            pass
    gone, still_alive = wait_procs(children, timeout=timeout)
    if including_parent:
        try:
            if verbose.kill:
                print("killing {}".format(parent.pid))
            parent.kill()
            parent.terminate()
            try:
                parent.wait(timeout)
            except TimeoutExpired:
                print("timeout expired, process may still be around: {}".format(parent.pid))
        except NoSuchProcess:
            pass

class verbose:
    kill = False


def gcd(*args):
    """
    Implement Euclid's algorithm for calculating the greatest common divisor.
    """
    args = list(args)
    assert all(x > 0 and isinstance(x, int) for x in args)
    assert len(args) >= 1
    while len(args) >= 2:
        args = list(set([x for x in args if x != 0]))
        m = min(args)
        args = [x % m if x != m else m for x in args]
    if len(args) == 1:
        return args[0]
    # error
    return None

