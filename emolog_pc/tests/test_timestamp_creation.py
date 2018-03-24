from datetime import datetime
from os import system, path, chdir
from emolog.dwarfutil import read_all_elf_variables
from tempfile import TemporaryDirectory
from sys import stderr


def create_c_file(target):
    ts = int(datetime.utcnow().timestamp() * 1000)
    with open(target, 'w+') as fd:
        fd.write(f"""// This is used to verify the binary file read by the PC matches the binary file burned into the hardware it's talking to:
const long long emolog_timestamp __attribute__((used)) = {ts};
#ifdef __TI_ARM__
#pragma RETAIN(emolog_timestamp)
#endif

int main(void)
{{
}}

""")
    return ts


def create_executable(source, target):
    system(f'gcc -ggdb -O3 -o {target} {source}')
    assert(path.exists(target))


def test_cycle():
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
