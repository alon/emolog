#!/usr/bin/env python3
from os import path
from os.path import join
from setuptools import setup, Extension
import shutil

try:
    import numpy
except:
    class numpy:
        @staticmethod
        def get_include():
            return ''
try:
    from Cython.Build import cythonize
except:
    use_cython = False
    def cythonize(*args, **kw):
        return args[0]
else:
    use_cython = True

gdb_debug = False
#macros = [('CYTHON_TRACE', 1)]
macros = []

# TODO - line tracing. compiler_directives no longer used
#                   compiler_directives={'linetrace': True, 'binding': True},
# gives
# extension.py:131: UserWarning: Unknown Extension options: 'compiler_directives'


# hack: copy files internally
# better solution: emolog-protocol package
for f in ["emolog_protocol.h", "emolog_protocol.cpp", 'emolog_debug.h']:
    src = path.join("..", "emolog_protocol", f)
    dst = path.join("emolog", "protocol", f)
    if not path.exists(dst):
        shutil.copyfile(src, dst)


if use_cython:
    print("*" * 10 + "WITH CYTHON" + "*" * 10)
    cylib = Extension(name='emolog.cylib',
                      sources=[join('emolog', 'cylib.pyx'), join('..', 'emolog_protocol', 'emolog_protocol.cpp')],
                      include_dirs=[join('..', 'emolog_protocol')] + [numpy.get_include()],
                      define_macros=macros,
                      language="c++")
    fakeembedded = Extension(name="emolog.fakeembedded", sources=[join('emolog', 'fakeembedded.pyx')])
    cython_util = Extension(name="emolog.cython_util", sources=[join('emolog', 'cython_util.pyx')])
    decoders = Extension(name="emolog.decoders", sources=[join('emolog', 'decoders.pyx')])
    cython_install_requires = [
        'Cython(==0.27.3)',
    ]
    cython_setup_requires = [
        'Cython(==0.27.3)',
    ]
else:
    cylib = Extension(name="emolog.cylib",
                      sources=[join('emolog', 'cylib.cpp'),
                               join('emolog', 'protocol', 'emolog_protocol.cpp'),
                               ],
                      include_dirs=[join('emolog', 'protocol')] + [numpy.get_include()],
                      define_macros=macros,
                      language="c++",
                      #data=[join('emolog', 'protocol', 'emolog_protocol.h')]
                      )
    fakeembedded = Extension(name="emolog.fakeembedded", sources=[join('emolog', 'fakeembedded.c')])
    cython_util = Extension(name="emolog.cython_util", sources=[join('emolog', 'cython_util.c')])
    decoders = Extension(name="emolog.decoders", sources=[join('emolog', 'decoders.c')])
    cython_setup_requires = cython_install_requires = []

cython_extensions = [cylib, fakeembedded, cython_util, decoders]

setup(
    name='emolog',
    description='Command & Control side for emolog protocol',
    version="0.1",
    setup_requires=[
        'setuptools>=18.0', # cython extensions
        'numpy'
    ] + cython_setup_requires,
    install_requires=[
        'pyelftools(==0.24)',
        'xlrd(==1.1.0)',
        'XlsxWriter(==1.0.2)',
        'pandas(==0.21.0)',
        'pyserial(==3.2.1)',
        'pyserial-asyncio(>=0.4)',
        'psutil(==5.4.1)',
        'colorama>=0.3.7',
    ] + cython_install_requires,
    extras_require={
        'pyinstaller': [
            'PyInstaller(==3.3)',
        ]
    },
    packages=['emolog', 'emolog.dwarf', 'emolog.emotool'],
    ext_modules = cythonize(cython_extensions, gdb_debug=gdb_debug),
    data_files=[
        (join('etc', 'emolog'), ['config/local_machine_config.ini.example']),
        (join('emolog', 'protocol'), ['emolog/protocol/emolog_debug.h'])
    ],
    entry_points={
        'console_scripts': [
            'emotool = emolog.emotool.main:main',
            'emogui = emolog.emotool.main_window:main',
        ]
    },
    classifiers = ['Development Status :: 3 - Alpha',
        'Environment :: Console',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GPL License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Topic :: Utilities',
    ],
)
