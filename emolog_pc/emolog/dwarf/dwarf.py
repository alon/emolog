#!/usr/bin/env python

"""

DWARF parser minimal implementation.

All references unless states otherwise are for:
    DWARF v3, December 20, 2005

"""

"""
Enumeration examples

TI ARM C/C++ Codegen PC v16.9.6.LTS
([], DIE DW_TAG_enumeration_type, size=13, has_children=True
    |DW_AT_sibling     :  AttributeValue(name='DW_AT_sibling', form='DW_FORM_ref4', value=327, raw_value=327, offset=90158)
    |DW_AT_name        :  AttributeValue(name='DW_AT_name', form='DW_FORM_strp', value=b'Direction', raw_value=10704, offset=90162)
    |DW_AT_byte_size   :  AttributeValue(name='DW_AT_byte_size', form='DW_FORM_data1', value=1, raw_value=1, offset=90166)
    |DW_AT_decl_column :  AttributeValue(name='DW_AT_decl_column', form='DW_FORM_data1', value=6, raw_value=6, offset=90167)
    |DW_AT_decl_file   :  AttributeValue(name='DW_AT_decl_file', form='DW_FORM_data1', value=1, raw_value=1, offset=90168)
    |DW_AT_decl_line   :  AttributeValue(name='DW_AT_decl_line', form='DW_FORM_data1', value=68, raw_value=68, offset=90169)
)

gcc 7.2.1 x86_64
typedef enum {
    DOWN=0,
    UP=-1
} direction_t;



([DIE DW_TAG_typedef, size=11, has_children=False
    |DW_AT_name        :  AttributeValue(name='DW_AT_name', form='DW_FORM_strp', value=b'direction_t', raw_value=3522, offset=7737)
    |DW_AT_decl_file   :  AttributeValue(name='DW_AT_decl_file', form='DW_FORM_data1', value=1, raw_value=1, offset=7741)
    |DW_AT_decl_line   :  AttributeValue(name='DW_AT_decl_line', form='DW_FORM_data1', value=199, raw_value=199, offset=7742)
    |DW_AT_type        :  AttributeValue(name='DW_AT_type', form='DW_FORM_ref4', value=2087, raw_value=2087, offset=7743)
, DIE DW_TAG_enumeration_type, size=13, has_children=True
    |DW_AT_encoding    :  AttributeValue(name='DW_AT_encoding', form='DW_FORM_data1', value=7, raw_value=7, offset=7712)
    |DW_AT_byte_size   :  AttributeValue(name='DW_AT_byte_size', form='DW_FORM_data1', value=4, raw_value=4, offset=7713)
    |DW_AT_type        :  AttributeValue(name='DW_AT_type', form='DW_FORM_ref4', value=51, raw_value=51, offset=7714)
    |DW_AT_decl_file   :  AttributeValue(name='DW_AT_decl_file', form='DW_FORM_data1', value=1, raw_value=1, offset=7718)
    |DW_AT_decl_line   :  AttributeValue(name='DW_AT_decl_line', form='DW_FORM_data1', value=196, raw_value=196, offset=7719)
    |DW_AT_sibling     :  AttributeValue(name='DW_AT_sibling', form='DW_FORM_ref4', value=2112, raw_value=2112, offset=7720)
], DIE DW_TAG_base_type, size=7, has_children=False
    |DW_AT_byte_size   :  AttributeValue(name='DW_AT_byte_size', form='DW_FORM_data1', value=4, raw_value=4, offset=5676)
    |DW_AT_encoding    :  AttributeValue(name='DW_AT_encoding', form='DW_FORM_data1', value=7, raw_value=7, offset=5677)
    |DW_AT_name        :  AttributeValue(name='DW_AT_name', form='DW_FORM_strp', value=b'unsigned int', raw_value=142, offset=5678)
)

"""

import sys
import logging
from functools import reduce

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

        self.interesting_vars = [v for v in var_descriptors if v.is_interesting()]

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

    def pretty_print(self, children=None, tab=0):
        if children is None:
            children = self.interesting_vars
        for v in children:
            print("{}{!s}".format('   ' * tab, v))
            self.pretty_print(children=v.children, tab=tab + 1)


DW_OP_plus_uconst = 0x23    # Page 20
DW_OP_addr = 0x3            # Page 14


class DwarfTypeMissingRequiredAttribute(Exception):
    def __init__(self, var, name):
        self.var = var
        self.name = name
        super().__init__(f'DWARF var {var.name} missing attribute {name}')


class VarDescriptor:

    uninteresting_var_names = ['main_func_sp', 'g_pfnVectors']

    DW_TAG_class_type = 'DW_TAG_class_type'
    DW_TAG_const_type = 'DW_TAG_const_type'
    DW_TAG_volatile_type = 'DW_TAG_volatile_type'
    DW_TAG_pointer_type = 'DW_TAG_pointer_type'
    DW_TAG_array_type = 'DW_TAG_array_type'
    DW_TAG_subrange_type = 'DW_TAG_subrange_type'
    DW_TAG_enumeration_type = 'DW_TAG_enumeration_type'
    DW_TAG_typedef = 'DW_TAG_typedef'

    type_tags_to_names = {DW_TAG_class_type: 'class',
                          DW_TAG_const_type: 'const',
                          DW_TAG_volatile_type: 'volatile',
                          DW_TAG_pointer_type: 'pointer to',
                          DW_TAG_array_type: 'array of',
                          DW_TAG_typedef: 'typedef'}

    DW_AT_name = 'DW_AT_name'
    DW_AT_type = 'DW_AT_type'
    DW_AT_external = 'DW_AT_external'
    DW_AT_location = 'DW_AT_location'
    DW_AT_decl_line = 'DW_AT_decl_line'
    DW_AT_byte_size = 'DW_AT_byte_size'
    DW_AT_upper_bound = 'DW_AT_upper_bound'
    DW_AT_data_member_location = 'DW_AT_data_member_location'

    ADDRESS_TYPE_UNSUPPORTED = '(Address Type Unsupported)'

    def __init__(self, all_dies, var_die, parent):
        self.parent = parent
        self.all_dies = all_dies
        self.var_die = var_die
        self.name = self.get_attribute_value(self.DW_AT_name, required=True).decode('utf-8')
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
        attr = self.get_attribute(self.DW_AT_data_member_location)
        if attr is None:
            return None
        assert self.parent is not None

        if attr.form == 'DW_FORM_block1':
            opcode = attr.value[0]
            if opcode != DW_OP_plus_uconst:
                return self.ADDRESS_TYPE_UNSUPPORTED
            offset = attr.value[1]
        elif attr.form in ['DW_FORM_data1', 'DW_FORM_data2', 'DW_FORM_data4']:
            offset = attr.value
        else:
            return self.ADDRESS_TYPE_UNSUPPORTED

        if not isinstance(self.parent.address, int):
            return self.ADDRESS_TYPE_UNSUPPORTED
        return self.parent.address + offset

    def _parse_location_attribute(self):
        loc = self.get_attribute(self.DW_AT_location)
        if loc is None:
            return None
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

    def _die_at_attr(self, die, attr_name):
        attr = die.attributes[attr_name]
        if attr.form == 'DW_FORM_ref_addr':
            die_offset = attr.value  # store offset is absolute offset in the DWARF info
        elif attr.form == 'DW_FORM_ref4':
            die_offset = attr.value + die.cu.cu_offset # Stored offset is relative to the current Compilation Unit
        else:
            return ("Unsupported form of the type attribute: %s" % attr.form)
        return self.all_dies[die_offset]


    def get_type_die(self, die):
        if 'DW_AT_type' not in die.attributes:
            return "No type die"
        type_die = self._die_at_attr(die, self.DW_AT_type)
        return type_die

    def is_interesting(self):
        # TODO: better criteria than the address?
        return (
            isinstance(self.address, int)       # either an address was not specified or is not a fixed address in RAM (local var, const in flash memory, etc)
            and not self.name.startswith('_')   # various system variables
            and not self.name.startswith('$')   # not sure when these pop up but they are not interesting
            and not self.name in VarDescriptor.uninteresting_var_names)

    def get_die_tags(self):
        type_chain, last_type = self.visit_type_chain()
        type_chain.append(last_type)
        return [die.tag for die in type_chain]

    def is_pointer(self):
        return self.DW_TAG_pointer_type in self.get_die_tags()

    def is_external(self):
        return self.get_attribute_value(self.DW_AT_external, False)

    def is_array(self):
        return self.get_array_type() is not None

    def is_enum(self):
        return self.get_enum_type() is not None

    def get_attribute(self, name, required=False):
        if name in self.var_die.attributes:
            return self.var_die.attributes[name]
        if required:
            raise DwarfTypeMissingRequiredAttribute(self, name)
        return None

    def get_attribute_value(self, name, default=None, required=False):
        attr = self.get_attribute(name, required=required)
        if attr is None:
            return default
        return attr.value

    def get_array_type(self):
        type_chain, last_type = self.visit_type_chain()
        type_chain.append(last_type)
        for die in type_chain:
            if die.tag == self.DW_TAG_array_type:
                return die
        return None

    def visit_type_chain(self):
        cur_type = self.type
        all_but_last = []
        while self.DW_AT_type in cur_type.attributes:     # while not the final link in the type-chain
            all_but_last.append(cur_type)
            cur_type = self.get_type_die(cur_type)
        return all_but_last, cur_type

    def visit_leafs(self):
        if self.children == []:
            yield self
        else:
            for child in self.children:
                yield from child.visit_leafs()

    def get_only_die_in_type_chain(self, tag, required=True):
        all_but_last, last_cur_type = self.visit_type_chain()
        with_tag = [x for x in all_but_last + [last_cur_type] if x.tag == tag]
        if not required and len(with_tag) == 0:
            return None
        assert len(with_tag) == 1, f'more than a single tag {tag} in {v}'
        return with_tag[0]

    def get_enum_type(self):
        return self.get_only_die_in_type_chain(self.DW_TAG_enumeration_type, required=False)

    def get_enum_dict(self):
        enum_type = self.get_enum_type()
        return {c.attributes['DW_AT_name'].value.decode('utf-8'):
                    c.attributes['DW_AT_const_value'].value
                for c in enum_type.iter_children()}

    def get_type_str(self):
        type_str = []
        all_but_last, last_cur_type = self.visit_type_chain()
        for cur_type in all_but_last:
            if cur_type.tag in self.type_tags_to_names:
                type_str.append(self.type_tags_to_names[cur_type.tag])
            elif cur_type.tag == self.DW_TAG_enumeration_type:
                continue # we handle this below
            else:
                type_str.append(cur_type.tag)

        enum_type = self.get_enum_type()
        if self.DW_AT_name in last_cur_type.attributes:
            if enum_type is not None:
                type_str.append('enum')
            type_str.append(last_cur_type.attributes['DW_AT_name'].value.decode('utf-8'))
        else:
            type_str.append('(unnamed variable)')

        return ' '.join(type_str)

    def get_array_sizes(self):
        res = []
        array_type = self.get_array_type()
        assert array_type is not None, f"cannot find array type in type chain: {self}"
        for child in array_type.iter_children():
            if self.DW_AT_upper_bound not in child.attributes:
                return None # better be safe - we don't know the meaning in this case.
            res.append(child.attributes[self.DW_AT_upper_bound].value + 1)
        return res

    def get_array_flat_length(self):
        bounds = self.get_array_sizes()
        if bounds is None or len(bounds) == 0:
            return None
        array_len = reduce(lambda x, y: x * y, bounds)
        return array_len

    def _get_byte_size_from_die(self, die):
        byte_size = die.attributes.get(self.DW_AT_byte_size, None)
        if byte_size is not None:
            assert(byte_size.form in ['DW_FORM_data1', 'DW_FORM_data2'])
            return byte_size.value
        return None

    def _get_size(self):
        type_chain, last_type = self.visit_type_chain()
        type_chain.append(last_type)

        # if there is no size to the final element return None. Seen for example
        # on an external pointer type:
        # DW_AT_external - __TI_Handler_Table_Base
        elem_size = self._get_byte_size_from_die(last_type)

        # if this is an array of anything (including array of arrays etc) take the size from the *first* array die
        # otherwise from the last die in the type-chain
        array_type = self.get_array_type()
        if array_type is not None:
            if self.DW_AT_byte_size in array_type.attributes:
                byte_size = self._get_byte_size_from_die(array_type)
            else:
                flat_length = self.get_array_flat_length()
                if flat_length is None:
                    # NOTE: we did not have to support these variables until
                    # now. For instance, sys_errlist when compiling on gcc with
                    # x86_64 the pc_platform example
                    return None
                byte_size = flat_length * elem_size
        else:
            byte_size = elem_size
        return byte_size

    def _create_children(self):
        all_but_last, last = self.visit_type_chain()
        if last.tag in {'DW_TAG_class_type', 'DW_TAG_structure_type'} and last.has_children:
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
        return self.get_attribute_value(self.DW_AT_decl_line, 'unknown')

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
