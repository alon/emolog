#!/bin/env python
import os
import sys

from emolog.emotool.main import dwarf_get_variables_by_name
from emolog.dwarf.dwarf import FileParser

basedir = os.path.dirname(__file__)
# snapshot_vars = open('snapshot_vars.csv').readlines()
one_shot_vars = ['controller.state.required_dir,0,1']
data = [
    #(os.path.join(basedir, 'tests', 'example.out'), ['var_unsigned_char,1,0', 'var_int,1,0', 'var_float,1,0', 'var_float_arr_2,1,0'])
    ('../../pump_drive/Release/pump_drive_tiva.out', None)
    #('../examples/pc_platform/pc', one_shot_vars)
    ]
for filename, vars in data:
    parsed = FileParser(filename)
    # 'var_float8,1,0',
    variables = dwarf_get_variables_by_name(filename, vars)
    timestamp = parsed.get_const_by_name('emolog_timestamp')
    for name, var in variables.items():
        print(f"=== {name} ===")
        for attr in ['type', 'size', 'get_array_sizes', 'get_enum_dict', 'get_full_name', 'get_type_str', 'visit_type_chain']:
            v = getattr(var, attr)
            if callable(v):
                try:
                    v = v()
                except:
                    continue
            print(f'  {str(attr):20} = {str(v).strip():20}')
        print()
    #var = {v['name']: v for v in variables}['controller.state.required_dir']
    #v = var['v']
    #decoder = var['_type']
    #import pdb; pdb.set_trace()
