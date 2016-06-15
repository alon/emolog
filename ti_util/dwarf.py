import sys

from elftools.elf.elffile import ELFFile


class VarDescriptor:
    all_dies = {}
    uninteresting_var_names = ['main_func_sp', 'g_pfnVectors']

    def __init__(self, var_die, parent):
        self.var_die = var_die
        self.name = var_die.attributes['DW_AT_name'].value.decode('utf-8')  # TODO is that the right way to do bytes -> str?
        self.address = self.parse_location()
        self.type = self.get_type_die(var_die)
        # TODO: children, parent

    @staticmethod
    def read_die_rec(die):
        VarDescriptor.all_dies[die.offset] = die
        for child in die.iter_children():
            VarDescriptor.read_die_rec(child)

    @staticmethod
    def read_dies_from_dwarf_file(filename):
        print('Processing file:', filename)
        with open(filename, 'rb') as f:
            elffile = ELFFile(f)
            if not elffile.has_dwarf_info():
                print('ERROR: file has no DWARF info')
                return

            dwarfinfo = elffile.get_dwarf_info()
            for CU in dwarfinfo.iter_CUs():
                top_DIE = CU.get_top_DIE()
                VarDescriptor.read_die_rec(top_DIE)
                # TEMP
                # lineprog = dwarfinfo.line_program_for_CU(CU)
                # print (len(lineprog.header.file_entry), lineprog.header.file_entry)
                # END TEMP

    def parse_location(self):
        # TODO: handle address parsing better and for more cases (using an interface for processing DWARF expressions?)
        if 'DW_AT_location' not in self.var_die.attributes:
            return "(No Address)"
        loc = self.var_die.attributes['DW_AT_location']
        if loc.form != 'DW_FORM_block1':
            return "(Address Type Unsupported)"
        if len(loc.value) != 5:
            return "(Address Type Unsupported)"
        if loc.value[0] != 3:
            return "(Address Type Unsupported)"
        a, b, c, d = loc.value[1:]
        return a + (b << 8) + (c << 16) + (d << 24)

    @staticmethod
    def get_type_die(die):
        type_attr = die.attributes['DW_AT_type']
        if type_attr.form == 'DW_FORM_ref_addr':
            type_die_offset = type_attr.value  # store offset is absolute offset in the DWARF info
        elif type_attr.form == 'DW_FORM_ref4':
            type_die_offset = type_attr.value + die.cu.cu_offset # Stored offset is relative to the current Compilation Unit
        else:
            return ("Unsupported form of the type attribute: %s" % type_attr.form)

        type_die = VarDescriptor.all_dies[type_die_offset]
        return type_die

    # def get_die_from_attr_ref(self, attribute):
    #     if attribute.form == 'DW_FORM_ref_addr':
    #         die_offset = attribute.value  # stored offset is absolute offset in the DWARF info
    #     elif attribute.form == 'DW_FORM_ref4':
    #         die_offset = attribute.value + self.var_die.cu.cu_offset  # Stored offset is relative to the current Compilation Unit
    #     else:
    #         return ("Unsupported form of the type attribute: %s" % attribute.form)
    #
    #     type_die = VarDescriptor.all_dies[die_offset]
    #     return (type_die)


    def is_interesting(self):
        # TODO: better criteria than the address?
        if not isinstance(self.address, int):   # either an address was not specified or is not a fixed address in RAM (local var, const in flash memory, etc)
            return False
        if self.name.startswith('_'):   # various system variables
            return False
        if self.name in VarDescriptor.uninteresting_var_names:
            return False
        return True

    def get_type_str(self):
        type_tags_to_names = {'DW_TAG_class_type': 'class',
                              'DW_TAG_const_type': 'const',
                              'DW_TAG_volatile_type': 'volatile',
                              'DW_TAG_pointer_type': 'pointer to',
                              'DW_TAG_array_type': 'array of'}  # TODO: move this?

        type_str = []
        cur_type = self.type
        while 'DW_AT_type' in cur_type.attributes:     # while not the final link in the type-chain
            if cur_type.tag in type_tags_to_names:
                type_str.append(type_tags_to_names[cur_type.tag])
            else:
                type_str.append(cur_type.tag)
            cur_type = VarDescriptor.get_type_die(cur_type)

        if 'DW_AT_name' in cur_type.attributes:
            type_str.append(cur_type.attributes['DW_AT_name'].value.decode('utf-8'))
        else:
            type_str.append('(unnamed variable)')

        return ' '.join(type_str)

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
        # return "<name: %s, type: %s, address: %s>" % (self.name, self.get_type_str(), hex(self.address))
        if isinstance(self.address, int):
            address_str = hex(self.address)
        else:
            address_str = self.address
        return "<%s %s @ %s (%s, line %s)>" % (self.get_type_str(), self.name, address_str, self.get_decl_file(), self.get_decl_line())

    __repr__ = __str__


if __name__ == '__main__':
    VarDescriptor.read_dies_from_dwarf_file(sys.argv[1])

    var_dies = {offset : die for (offset, die) in VarDescriptor.all_dies.items() if die.tag == 'DW_TAG_variable'}
    print("read %d DIEs which include %d variable DIEs" % (len(VarDescriptor.all_dies), len(var_dies)))

    vars = []
    for (offset, var_die) in var_dies.items():
        vars.append(VarDescriptor(var_die, None))

    interesting_vars = [v for v in vars if v.is_interesting()]
    interesting_vars[2].get_type_str()  #TEMP
    pass