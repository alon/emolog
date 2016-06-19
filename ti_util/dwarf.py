import sys

from elftools.elf.elffile import ELFFile


class FileParser:
    def __init__(self, filename):
        self.all_dies = {}
        self.read_dies_from_dwarf_file(filename)

        var_dies = {offset: die for offset, die in self.all_dies.items() if die.tag == 'DW_TAG_variable'}
        print("read %d DIEs which include %d variable DIEs" % (len(self.all_dies), len(var_dies)))

        self.var_descriptors = var_descriptors = []
        for offset, var_die in var_dies.items():
            var_descriptors.append(VarDescriptor(self.all_dies, var_die, None))

        self.interesting_vars = interesting_vars = [v for v in var_descriptors if v.is_interesting()]
        pass

    def read_dies_from_dwarf_file(self, filename):
        print('Processing file:', filename)
        with open(filename, 'rb') as f:
            elffile = ELFFile(f)
            if not elffile.has_dwarf_info():
                print('ERROR: file has no DWARF info')
                return

            dwarfinfo = elffile.get_dwarf_info()
            for CU in dwarfinfo.iter_CUs():
                top_DIE = CU.get_top_DIE()
                self.read_die_rec(top_DIE)

    def read_die_rec(self, die):
        self.all_dies[die.offset] = die
        for child in die.iter_children():
            self.read_die_rec(child)

    def visit_interesting_vars_tree_leafs(self):
        for v in self.interesting_vars:
            yield from v.visit_leafs()

    def pretty_print(self, children = None, tab=0):
        if children is None:
            children = self.interesting_vars
        for v in children:
            print("{}{!s}".format('   ' * tab, v))
            self.pretty_print(children=v.children, tab=tab + 1)


DW_OP_plus_uconst = 0x23 # DWARF v3 page 20, December 20, 2005
DW_OP_addr = 0x3 # Page 14


class VarDescriptor:

    uninteresting_var_names = ['main_func_sp', 'g_pfnVectors']

    def __init__(self, all_dies, var_die, parent):
        self.parent = parent
        self.all_dies = all_dies
        self.var_die = var_die
        self.name = var_die.attributes['DW_AT_name'].value.decode('utf-8')  # TODO is that the right way to do bytes -> str?
        self.address = self.parse_location()
        self.type = self.get_type_die(var_die)
        self.size = self._get_size()
        if not self.is_pointer():
            self.children = self._create_children()
        else:
            self.children = []

    def parse_location(self):
        # TODO: handle address parsing better and for more cases (using an interface for processing DWARF expressions?)
        ret = self._parse_member_location()
        if ret is None:
            ret = self._parse_location_attribute()
        if ret is None:
            ret = "(No Address)"
        return ret

    def _parse_member_location(self):
        if not 'DW_AT_data_member_location' in self.var_die.attributes:
            return None
        assert self.parent is not None
        attr = self.var_die.attributes['DW_AT_data_member_location']
        assert attr.form == 'DW_FORM_block1'
        opcode = attr.value[0]
        if opcode != DW_OP_plus_uconst:
            return '(Address Type of data member is Unsupported)'
        offset = attr.value[1]
        if not isinstance(self.parent.address, int):
            return 0
        return self.parent.address + offset

    def _parse_location_attribute(self):
        if 'DW_AT_location' not in self.var_die.attributes:
            return None
        loc = self.var_die.attributes['DW_AT_location']
        opcode = loc.value[0]
        if loc.form != 'DW_FORM_block1':
            return "(Address Type Unsupported)"
        if len(loc.value) != 5:
            return "(Address Type Unsupported)"
        if opcode != DW_OP_addr:
            return "(Address Type Unsupported)"
        a, b, c, d = loc.value[1:]
        return a + (b << 8) + (c << 16) + (d << 24)

    def get_type_die(self, die):
        type_attr = die.attributes['DW_AT_type']
        if type_attr.form == 'DW_FORM_ref_addr':
            type_die_offset = type_attr.value  # store offset is absolute offset in the DWARF info
        elif type_attr.form == 'DW_FORM_ref4':
            type_die_offset = type_attr.value + die.cu.cu_offset # Stored offset is relative to the current Compilation Unit
        else:
            return ("Unsupported form of the type attribute: %s" % type_attr.form)

        type_die = self.all_dies[type_die_offset]
        return type_die

    def is_interesting(self):
        # TODO: better criteria than the address?
        if not isinstance(self.address, int):   # either an address was not specified or is not a fixed address in RAM (local var, const in flash memory, etc)
            return False
        if self.name.startswith('_'):   # various system variables
            return False
        if self.name in VarDescriptor.uninteresting_var_names:
            return False
        return True

    DW_TAG_pointer_type = 'DW_TAG_pointer_type'

    def is_pointer(self):
        type_chain, last_type = self.visit_type_chain()
        type_chain.append(last_type)
        type_tags = [die.tag for die in type_chain]
        return self.DW_TAG_pointer_type in type_tags

    type_tags_to_names = {'DW_TAG_class_type': 'class',
                          'DW_TAG_const_type': 'const',
                          'DW_TAG_volatile_type': 'volatile',
                          DW_TAG_pointer_type: 'pointer to',
                          'DW_TAG_array_type': 'array of'}

    def visit_type_chain(self):
        cur_type = self.type
        all_but_last = []
        while 'DW_AT_type' in cur_type.attributes:     # while not the final link in the type-chain
            all_but_last.append(cur_type)
            cur_type = self.get_type_die(cur_type)
        return all_but_last, cur_type

    def visit_leafs(self):
        if self.children == []:
            yield self
        else:
            for child in self.children:
                yield from child.visit_leafs()

    def get_type_str(self):
        type_str = []
        all_but_last, last_cur_type = self.visit_type_chain()
        for cur_type in all_but_last:
            if cur_type.tag in self.type_tags_to_names:
                type_str.append(self.type_tags_to_names[cur_type.tag])
            else:
                type_str.append(cur_type.tag)

        if 'DW_AT_name' in last_cur_type.attributes:
            type_str.append(last_cur_type.attributes['DW_AT_name'].value.decode('utf-8'))
        else:
            type_str.append('(unnamed variable)')

        return ' '.join(type_str)

    def _get_size(self):
        _all_but_last, last = self.visit_type_chain()
        byte_size = last.attributes.get('DW_AT_byte_size', None)
        if byte_size is not None:
            assert byte_size.form == 'DW_FORM_data1'
            return byte_size.value
        return None # we don't know or there is no size to this DIE

    def _create_children(self):
        all_but_last, last = self.visit_type_chain()
        if last.tag in {'DW_TAG_class_type', 'DW_TAG_structure_type'}:
            assert last.has_children
            return [VarDescriptor(self.all_dies, v, self) for v in last.iter_children() if v.tag == 'DW_TAG_member']
        return []

    def get_full_name(self):
        if self.parent is None:
            return self.name
        return self.parent.get_full_name() + '.' + self.name

    def get_decl_file(self):
        # TODO: this is oversimplifying, it reports only the main file of the compilation unit.
        # TODO: if the variable is in a non-main file (such as a .h file) it will probably not be reported correctly.
        # TODO: the correct way is to read the DW_AT_decl_file attribute, it's an index to a table of files in
        # TODO: the compilation unit. the table is MAYBE the one in cu.dwarfinfo.line_program_for_CU(cu).header.file_entry
        # TODO: but the indexes don't match... perhaps zero-based instead of starting at 1...? check this.
        return self.var_die.cu.get_top_DIE().attributes['DW_AT_name'].value.decode('utf-8')

    def get_decl_line(self):
        if 'DW_AT_decl_line' not in self.var_die.attributes:
            return 'unknown'
        return self.var_die.attributes['DW_AT_decl_line'].value

    def __str__(self):
        if isinstance(self.address, int):
            address_str = hex(self.address)
        else:
            address_str = self.address
        return "<%s %s @ %s (%s, line %s)>" % (self.get_type_str(), self.get_full_name(), address_str, self.get_decl_file(), self.get_decl_line())

    __repr__ = __str__


def main():
    parser = FileParser(sys.argv[1])
    parser.pretty_print()
    pass

if __name__ == '__main__':
    main()