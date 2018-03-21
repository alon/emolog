import logging
from string import ascii_lowercase
import sys

from .dwarf import FileParser
from .decoders import Decoder, ArrayDecoder, NamedDecoder, unpack_str_from_size
from .varsfile import read_vars_file, parse_vars_definition, VarsFileError


logger = logging.getLogger()


def with_errors(s):
    # TODO - find a library for this? using error distance
    #  deleted element
    for i in range(0, len(s)):
        yield s[:i] + s[i + 1:]
    # rotated adjacent elements
    for i in range(0, len(s) - 1):
        yield s[:i] + s[i + 1] + s[i] + s[i + 2:]
    if len(s) > 3:
        # 26**3 is already ~ 1e5 is too much
        return
    # single complete alphabet typing errors - this is really large..
    for i in range(0, len(s)):
        for other in ascii_lowercase:
            yield s[:i] + other + s[i + 1:]


def dwarf_get_variables_by_name(filename, names):
    regular_mode = names is not None and len(names) > 0
    if names is None:
        names = []
    name_filter = (lambda v_name: v_name in names) if regular_mode else (lambda v_name: True)
    missing_check = (lambda found, given: given != found) if regular_mode else (lambda found, given: False)
    file_parser = FileParser(filename=filename)
    sampled_vars = {}
    found = set()
    elf_vars = list(file_parser.visit_interesting_vars_tree_leafs())
    elf_var_names = [v.get_full_name() for v in elf_vars]
    lower_to_actual = {name.lower(): name for name in elf_var_names}
    elf_var_names_set_lower = set(lower_to_actual.keys())
    logger.debug('candidate variables found in ELF file:')
    for v in elf_vars:
        v_name = v.get_full_name()
        logger.debug("candidate var: {}".format(v_name))
        if name_filter(v_name):
            if v.address == v.ADDRESS_TYPE_UNSUPPORTED:
                logger.error("Address type not supported for requested variable '{}'".format(v_name))
                raise SystemExit
            sampled_vars[v_name] = v
            found.add(v_name)
    given = set(names)
    if missing_check(found, given):
        logger.error("the following variables were not found in the ELF:\n{}".format(", ".join(list(given - found))))
        elf_name_to_options = {name: set(with_errors(name)) for name in elf_var_names_set_lower}
        missing_lower = [name.lower() for name in given - found]
        missing_lower_to_actual = {name.lower(): name for name in given - found}
        missing_to_errors = {name: set(with_errors(name)) for name in missing_lower}
        for name in missing_lower:
            options = [elf_name for elf_name, elf_options in elf_name_to_options.items() if
                       len(missing_to_errors[name] & elf_options) > 0]
            if len(options) > 0:
                print("{} is close to {}".format(missing_lower_to_actual[name],
                                                 ", ".join(lower_to_actual[x] for x in options)))
        sys.exit(-1)
    logger.info("Registering variables from {}".format(filename))
    for v in sampled_vars.values():
        logger.info("   {}".format(v.get_full_name()))
    return sampled_vars


class VariableNotSupported(Exception):
    def __init__(self, v, size):
        super().__init__(f'{v}: {size}')


unpack_str_from_type_name = dict(
    float=b'f',
    int=b'i',
    unsigned=b'I',
    short=b'h',
)


def variable_to_decoder(v, type_name, size):
    # NOTE: function accepts type_name and size as parameters instead of directly getting those from v so that
    # it would be able to call itself recursively with the element of an array
    name_bytes = v.name.encode('utf-8')
    if type_name.startswith('enum '):
        name_to_val = v.get_enum_dict()
        max_unsigned_val = 1 << (size * 8)
        val_to_name = {v: k for k, v in name_to_val.items()}
        return NamedDecoder(name=name_bytes, max_unsigned_val=max_unsigned_val, unpack_str=unpack_str_from_size(size), val_to_name=val_to_name)

    elif v.is_array():
        # this currently flattens multi-dimensional arrays to a long one dimensional array
        elem_type = type_name.rsplit(' ', 1)[1]
        elem_unpack_str = unpack_str_from_type_name[elem_type]
        assert len(elem_unpack_str) == 1
        array_len = v.get_array_flat_length()
        if size is None:
            raise VariableNotSupported(v, size)
        elem_size = int(size / array_len)
        assert (elem_size * array_len == size)
        return ArrayDecoder(name=name_bytes, elem_unpack_str=elem_unpack_str, length=array_len)

    elif type_name.endswith('float'):
        if size == 4:
            return Decoder(name=name_bytes, unpack_str=b'f')

    elif type_name.endswith('bool'):
        return NamedDecoder(name=name_bytes, max_unsigned_val=2, unpack_str=b'b', val_to_name={1: 'True', 0: 'False'})

    else:  # TODO this should be "if it's an int". also should handle signed/unsigned correctly
        unpack_str = unpack_str_from_size(size)
        return Decoder(name=name_bytes, unpack_str=unpack_str)

    raise VariableNotSupported(v, size)


def variables_from_dwarf_variables(names, name_to_ticks_and_phase, dwarf_variables, skip_not_supported):
    variables = []
    for name in names:
        v = dwarf_variables[name]
        period_ticks, phase_ticks = name_to_ticks_and_phase[name]
        try:
            decoder = variable_to_decoder(v=v, type_name=v.get_type_str(), size=v.size)
        except VariableNotSupported:
            if skip_not_supported:
                print(f"debug: unsupported by our DWARF DIE parser (dwarf package): {name}")
                continue
            raise
        variables.append(dict(
            name=name,
            phase_ticks=phase_ticks,
            period_ticks=period_ticks,
            address=v.address,
            size=v.size,
            v=v,
            _type=decoder))
    return variables


class DwarfFakeVariable:
    type_data = {float: dict(type_str='float', size=4)}

    next_address = 0

    @classmethod
    def allocate(cls, size):
        ret = cls.next_address
        cls.next_address += size
        return ret

    def __init__(self, name, type):
        self.type = type
        self.type_str = self.type_data[type]['type_str']
        self.name = name
        size = self.type_data[type]['size']
        self.address = DwarfFakeVariable.allocate(size)
        self.size = size

    def get_type_str(self):
        return self.type_str

    def is_array(self):
        return False


def fake_dwarf(names):
    def fake_variable(name):
        return DwarfFakeVariable(name, type=float)
    return {name: fake_variable(name) for name in names}


def read_elf_variables(elf, vars, varfile, skip_not_supported=False):
    if vars is None: # debug - will take all vars in ELF - usually not what you want
        return read_all_elf_variables(elf)
    num_command_line_args = len(vars)
    if varfile is not None:
        vars.extend(read_vars_file(varfile, check_errors=False))
    if len(vars) == 0:
        logger.error('no variable definitions supplied. use --var or --varsfile')
        raise SystemExit
    try:
        # Note hack: using negative numbers for command line arguments.
        # rust: would have used an enum :)
        split_vars = [parse_vars_definition(line=v, linenumber=i - num_command_line_args) for i, v in enumerate(vars)]
    except VarsFileError as e:
        logger.error(str(e))
        raise SystemExit
    names = [name for name, ticks, phase in split_vars]
    if elf is None:
        dwarf_variables = fake_dwarf(names)
    else:
        dwarf_variables = dwarf_get_variables_by_name(elf, names)
    if len(dwarf_variables) == 0:
        logger.error("no variables set for sampling")
        raise SystemExit
    name_to_ticks_and_phase = {name: (int(ticks), int(phase)) for name, ticks, phase in split_vars}
    return names, variables_from_dwarf_variables(
        names=names,
        name_to_ticks_and_phase=name_to_ticks_and_phase,
        dwarf_variables=dwarf_variables,
        skip_not_supported=skip_not_supported)


def read_all_elf_variables(elf):
    dwarf_variables = dwarf_get_variables_by_name(elf, None)
    names = list(sorted(dwarf_variables.keys()))
    name_to_ticks_and_phase = {k: (1, 0) for k in names}
    return names, variables_from_dwarf_variables(
        names, name_to_ticks_and_phase, dwarf_variables, skip_not_supported=True)


def main_dump():
    import argparse
    import os
    from pprint import pprint
    parser = argparse.ArgumentParser()
    parser.add_argument('-e', '--elf', required=True, type=str, help='ELF file')
    args = parser.parse_args()
    if not os.path.exists(args.elf):
        print(f"error: missing file {args.elf}")
        raise SystemExit
    out = read_elf_variables(elf=args.elf, vars=None, varfile=args.vars)
    pprint(out)


def main():
    import argparse
    import os
    from pprint import pprint
    parser = argparse.ArgumentParser()
    parser.add_argument('-e', '--elf', required=True, type=str, help='ELF file')
    parser.add_argument('-v', '--vars', required=True, type=str, help='vars file')
    parser.add_argument('--verbose', action='store_true', default=False, help='verbose')
    # slight logic duplication with emotool.main, but at least in one project
    args = parser.parse_args()
    if not os.path.exists(args.elf):
        print(f"error: missing file {args.elf}")
        raise SystemExit
    if not os.path.exists(args.vars):
        print(f"error: missing file {args.vars}")
        raise SystemExit
    # TODO: read_elf_variables abuses vars=None to mean no check; make the
    # argument explicit
    out = read_elf_variables(elf=args.elf, vars=[], varfile=args.vars)
    if args.verbose:
        pprint(out)
    print("ok")
