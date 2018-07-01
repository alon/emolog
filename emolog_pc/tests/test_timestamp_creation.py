from datetime import datetime
from os import system, path, chdir
from emolog.dwarfutil import read_all_elf_variables
from tempfile import TemporaryDirectory
import sys


def create_c_file(target):
    ts = int(datetime.now().timestamp() * 1000)
    with open(target, 'w+') as fd:
        fd.write("""// This is used to verify the binary file read by the PC matches the binary file burned into the hardware it's talking to:
const long long emolog_timestamp __attribute__((used)) = {ts};
#ifdef __TI_ARM__
#pragma RETAIN(emolog_timestamp)
#endif

int main(void)
{{
}}

""".format(ts=ts))
    return ts


def create_executable(source, target):
    system('gcc -ggdb -O3 -o {target} {source}'.format(**locals()))
    assert(path.exists(target))


def test_cycle():
    # broken under windows for now.
    if sys.platform == 'win32':
        return
    with TemporaryDirectory() as d:
        chdir(d)
        timestamp = create_c_file('timestamp.c')
        create_executable('timestamp.c', 'timestamp')
        names, variables = read_all_elf_variables('timestamp')
        assert names == ['emolog_timestamp']
        assert len(variables) == 1
        v = variables[0]
        init_value = v['init_value']
        assert init_value == timestamp


if __name__ == '__main__':
    test_cycle()
