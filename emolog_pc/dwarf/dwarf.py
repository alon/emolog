#!/usr/bin/env python

"""

DWARF parser minimal implementation.

All references unless states otherwise are for:
    DWARF v3, December 20, 2005

"""

import sys
import logging

from elftools.elf.elffile import ELFFile


logger = logging.getLogger('dwarf')


class FileParser:
    def __init__(self, filename):
        self.all_dies = {}
        self.read_dies_from_dwarf_file(filename)

        var_dies = {offset: die for offset, die in self.all_dies.items() if die.tag == 'DW_TAG_variable' and 'DW_AT_type' in die.attributes}
        logger.debug("read %d DIEs which include %d variable DIEs" % (len(self.all_dies), len(var_dies)))

        self.var_descriptors = var_descriptors = []
        for offset, var_die in var_dies.items():
            var_descriptors.append(VarDescriptor(self.all_dies, var_die, None))

        self.interesting_vars = interesting_vars = [v for v in var_descriptors if v.is_interesting()]

    def read_dies_from_dwarf_file(self, filename):
        logger.debug('Processing file: {}'.format(filename))
        with open(filename, 'rb') as f:
            elffile = ELFFile(f)
            if not elffile.has_dwarf_info():
                logger.error('file has no DWARF info')
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


DW_OP_plus_uconst = 0x23    # Page 20
DW_OP_addr = 0x3            # Page 14


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

    ADDRESS_TYPE_UNSUPPORTED = '(Address Type Unsupported)'

    def _parse_member_location(self):
        if not 'DW_AT_data_member_location' in self.var_die.attributes:
            return None
        assert self.parent is not None
        attr = self.var_die.attributes['DW_AT_data_member_location']
        if attr.form != 'DW_FORM_block1':
            return self.ADDRESS_TYPE_UNSUPPORTED
        opcode = attr.value[0]
        if opcode != DW_OP_plus_uconst:
            return self.ADDRESS_TYPE_UNSUPPORTED
        offset = attr.value[1]
        if not isinstance(self.parent.address, int):
            return 0
        return self.parent.address + offset

    def _parse_location_attribute(self):
        if 'DW_AT_location' not in self.var_die.attributes:
            return None
        loc = self.var_die.attributes['DW_AT_location']
        if loc.form == 'DW_FORM_exprloc':
            return self._parse_address_exprloc(loc)
        elif loc.form == 'DW_FORM_block1':
            return self._parse_address_block1(loc)
        return self.ADDRESS_TYPE_UNSUPPORTED

    def _parse_address_exprloc(self, loc):
        # TODO right now only supporting exprloc of the same format as block1:
        return self._parse_address_block1(loc)

    def _parse_address_block1(self, loc):
        opcode = loc.value[0]
        if len(loc.value) != 5 or opcode != DW_OP_addr:
            return self.ADDRESS_TYPE_UNSUPPORTED
        a, b, c, d = loc.value[1:]
        return a + (b << 8) + (c << 16) + (d << 24)

    def get_type_die(self, die):
        if 'DW_AT_type' not in die.attributes:
            return "No type die"
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
        return (
            isinstance(self.address, int)       # either an address was not specified or is not a fixed address in RAM (local var, const in flash memory, etc)
            and not self.name.startswith('_')   # various system variables
            and not self.name.startswith('$')   # not sure when these pop up but they are not interesting
            and not self.name in VarDescriptor.uninteresting_var_names)

    DW_TAG_class_type = 'DW_TAG_class_type'
    DW_TAG_const_type = 'DW_TAG_const_type'
    DW_TAG_volatile_type = 'DW_TAG_volatile_type'
    DW_TAG_pointer_type = 'DW_TAG_pointer_type'
    DW_TAG_array_type = 'DW_TAG_array_type'
    DW_TAG_typedef = 'DW_TAG_typedef'
    DW_TAG_subrange_type = 'DW_TAG_subrange_type'

    type_tags_to_names = {DW_TAG_class_type: 'class',
                          DW_TAG_const_type: 'const',
                          DW_TAG_volatile_type: 'volatile',
                          DW_TAG_pointer_type: 'pointer to',
                          DW_TAG_array_type: 'array of',
                          DW_TAG_typedef: 'typedef'}

    def is_pointer(self):
        type_chain, last_type = self.visit_type_chain()
        type_chain.append(last_type)
        type_tags = [die.tag for die in type_chain]
        return self.DW_TAG_pointer_type in type_tags

    def is_array(self):
        type_chain, last_type = self.visit_type_chain()
        type_chain.append(last_type)
        type_tags = [die.tag for die in type_chain]
        return self.DW_TAG_array_type in type_tags

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

    def get_enum_dict(self):
        all_but_last, last_cur_type = self.visit_type_chain()
        assert last_cur_type.tag == 'DW_TAG_enumeration_type'
        return {c.attributes['DW_AT_name'].value.decode('utf-8'):
                    c.attributes['DW_AT_const_value'].value
                for c in last_cur_type.iter_children()}

    def get_type_str(self):
        type_str = []
        all_but_last, last_cur_type = self.visit_type_chain()
        for cur_type in all_but_last:
            if cur_type.tag in self.type_tags_to_names:
                type_str.append(self.type_tags_to_names[cur_type.tag])
            else:
                type_str.append(cur_type.tag)

        if 'DW_AT_name' in last_cur_type.attributes:
            if last_cur_type.tag == 'DW_TAG_enumeration_type':
                type_str.append('enum')
            type_str.append(last_cur_type.attributes['DW_AT_name'].value.decode('utf-8'))
        else:
            type_str.append('(unnamed variable)')

        return ' '.join(type_str)

    def get_array_sizes(self):
        res = []
        for child in self.type.iter_children():
            res.append(child.attributes['DW_AT_upper_bound'].value + 1)
        return res

    def _get_size(self):
        type_chain, last_type = self.visit_type_chain()
        type_chain.append(last_type)

        # if this is an array of anything (including array of arrays etc) take the size from the *first* array die
        # otherwise from the last die in the type-chain
        array_type_dies = [die for die in type_chain if die.tag == self.DW_TAG_array_type]
        if array_type_dies != []:
            die_with_relevant_size = array_type_dies[0]
        else:
            die_with_relevant_size = last_type

        byte_size = die_with_relevant_size.attributes.get('DW_AT_byte_size', None)
        if byte_size is not None:
            assert(byte_size.form in ['DW_FORM_data1', 'DW_FORM_data2'])
            return byte_size.value
        return None # we don't know or there is no size to this DIE

    def _create_children(self):
        all_but_last, last = self.visit_type_chain()
        if last.tag in {'DW_TAG_class_type', 'DW_TAG_structure_type'}:
            assert last.has_children
            return [VarDescriptor(self.all_dies, v, self) for v in last.iter_children() if v.tag == 'DW_TAG_member' and 'DW_AT_type' in v.attributes]
        return []

    def get_full_name(self):
        if self.parent is None:
            return self.name
        return self.parent.get_full_name() + '.' + self.name

    def get_decl_file(self):
        # TODO: not sure if this is fully correct. two file name get methods are currently implemented.
        # TODO: when one doesn't work, we use the other. this is obviously not the best approach.
        # TODO: understand what is the definitive way to get the file name and implemnent it...
        if 'DW_AT_name' in self.var_die.cu.get_top_DIE().attributes:
            return self.var_die.cu.get_top_DIE().attributes['DW_AT_name'].value.decode('utf-8')
        else:
            cu = self.var_die.cu
            files = cu.dwarfinfo.line_program_for_CU(cu).header.file_entry
            return files[0]['name'].decode('utf-8')

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
