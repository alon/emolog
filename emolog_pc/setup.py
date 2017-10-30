import shutil
import os
import sys
from setuptools import setup

from Cython.Build import cythonize

from emolog import build_protocol_library, LIB_FILENAME, DEVEL_EMO_MESSAGE_TYPE_H_FILENAME


print(f"building {LIB_FILENAME}")
protocol_lib_path = build_protocol_library()
print(f"copying {LIB_FILENAME}")
shutil.copy(protocol_lib_path, 'emolog')
MESSAGE_TYPE_H_FILENAME = os.path.basename(DEVEL_EMO_MESSAGE_TYPE_H_FILENAME)
print(f"copying {MESSAGE_TYPE_H_FILENAME}")
shutil.copy(DEVEL_EMO_MESSAGE_TYPE_H_FILENAME, 'emolog')

setup(
    name='Emotool',
    description='Command & Control side for emolog protocol',
    version="0.1",
    install_requires=[
        'pyelftools(==0.24)',
        'pyqtgraph(==0.10.0)',
        'Qt.py(==1.0.0)',
        'Quamash(==0.5.5)',
        'PyQt5(==5.9)',
        'xlrd(==1.1.0)',
        'XlsxWriter(==1.0.2)',
        'pandas(==0.21.0)',
        'Cython(==0.27.2)',
        'pyserial(==3.2.1)',
        'pyserial-asyncio(==0.2)',
    ],
    packages=['emolog', 'emolog.dwarf', 'emolog.emotool'],
    package_data={'emolog': [LIB_FILENAME, MESSAGE_TYPE_H_FILENAME]},
    ext_modules = cythonize("emolog/cython_util.pyx"),
    data_files=[('etc/emolog', ['local_machine_config.ini.example'])],
    scripts=['scripts/emotool.py'],
)