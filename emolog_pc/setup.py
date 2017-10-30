import shutil
import os
import sys
from distutils.core import setup

from Cython.Build import cythonize

if 'win' in sys.platform:
    import py2exe

from emolog import build_protocol_library, LIB_FILENAME, DEVEL_EMO_MESSAGE_TYPE_H_FILENAME


print(f"building {LIB_FILENAME}")
protocol_lib_path = build_protocol_library()
print(f"copying {LIB_FILENAME}")
shutil.copy(protocol_lib_path, 'emolog')
MESSAGE_TYPE_H_FILENAME = os.path.basename(DEVEL_EMO_MESSAGE_TYPE_H_FILENAME)
print(f"copying {MESSAGE_TYPE_H_FILENAME}")
shutil.copy(DEVEL_EMO_MESSAGE_TYPE_H_FILENAME, 'emolog')

kw = dict(
    name = 'Emotool',
    description='Command & Control side for emolog protocol',
    packages=['emolog', 'emolog.dwarf', 'emolog.emotool'],
    package_data={'emolog': [LIB_FILENAME, MESSAGE_TYPE_H_FILENAME]},
    ext_modules = cythonize("emolog/cython_util.pyx"),
    scripts=['scripts/emotool.py'],
    data_files=[('etc/emolog', ['local_machine_config.ini.example'])],
)

if 'win' in sys.platform:
    kw['console'] = ['scripts/emotool.py']

setup(**kw)
