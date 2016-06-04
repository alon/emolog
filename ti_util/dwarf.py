import sys

from elftools.elf.elffile import ELFFile


def get_vars_from_dwarf(filename):
    print('Processing file:', filename)
    with open(filename, 'rb') as f:
        elffile = ELFFile(f)

        if not elffile.has_dwarf_info():
            print('  file has no DWARF info')
            return []

        dwarfinfo = elffile.get_dwarf_info()

        all_dies = {}
        for CU in dwarfinfo.iter_CUs():
            top_DIE = CU.get_top_DIE()
            read_die_rec(top_DIE, all_dies)

    var_dies = {offset : die for (offset, die) in all_dies.items() if die.tag == 'DW_TAG_variable'}
    print ("read %d DIE's which include %d variable DIEs" % (len(all_dies), len(var_dies)))

    vars = []
    for (offset, var_die) in var_dies.items():
        var = {}
        var['name'] = var_die.attributes['DW_AT_name'].value.decode('utf-8') #TODO is that the right way to do bytes -> str?
        var['address'] = parse_location(var_die)
        var['type'] = parse_type(var_die, all_dies)
        vars.append(var)
    interesting_vars = [v for v in vars if is_interesting(v)]
    return interesting_vars


def parse_location(var_die):
    # TODO: handle address parsing better and for more cases (using an interface for processing DWARF expressions?)
    if 'DW_AT_location' not in var_die.attributes:
        return None
    loc = var_die.attributes['DW_AT_location']
    if loc.form != 'DW_FORM_block1':
        return "Address Type Unsupported"
    if len(loc.value) != 5:
        return "Address Type Unsupported"
    if loc.value[0] != 3:
        return "Address Type Unsupported"
    return ((loc.value[1] + (loc.value[2] << 8) + (loc.value[3] << 16) + (loc.value[4] << 24)))


def parse_type(var_die, all_dies):
    type_attr = var_die.attributes['DW_AT_type']
    if type_attr.form == 'DW_FORM_ref_addr':
        type_die_offset = type_attr.value  # store offset is absolute offset in the DWARF info
    elif type_attr.form == 'DW_FORM_ref4':
        type_die_offset = type_attr.value + var_die.cu.cu_offset # Stored offset is relative to the current Compilation Unit
    else:
        return ("Unsupported form of the type attribute: %s" % type_attr.form)

    type_die = all_dies[type_die_offset]
    return(type_die)


def is_interesting(var):
    uninteresting_vars = ['main_func_sp', 'g_pfnVectors']
    # TODO: "unsupported address" is probably not the best criteria, should be improved
    if var['address'] == None or var['address'] == 'Address Type Unsupported':
        return False
    if var['name'].startswith('_'): # various system variables
        return False
    if var['name'] in uninteresting_vars:
        return False
    return True


def read_die_rec(die, die_dict):
    die_dict[die.offset] = die
    for child in die.iter_children():
        read_die_rec(child, die_dict)


if __name__ == '__main__':
    get_vars_from_dwarf(sys.argv[1])
