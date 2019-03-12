#!/usr/bin/env python3
from os import path, chdir
from os.path import join
from setuptools import setup, Extension
import shutil
from emolog import VERSION

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

setup_root = path.abspath(path.dirname(__file__))
emolog_root = path.join(setup_root, 'emolog')
emolog_protocol_root = path.join(setup_root, '..', 'emolog_protocol')

# allow running from different directory
chdir(setup_root)

# hack: copy files internally
# better solution: emolog-protocol package
for f in ["emolog_protocol.h", "emolog_protocol.cpp", 'emolog_debug.h']:
    src = path.join(emolog_protocol_root, f)
    dst = path.join(emolog_root, 'protocol', f)
    if not path.exists(dst):
        shutil.copyfile(src, dst)


if use_cython:
    cylib = Extension(name='emolog.cylib',
                      sources=[join(emolog_root, 'cylib.pyx'), join(emolog_protocol_root, 'emolog_protocol.cpp')],
                      include_dirs=[emolog_protocol_root] + [numpy.get_include()],
                      define_macros=macros,
                      language="c++")
    fakeembedded = Extension(name="emolog.fakeembedded", sources=[join(emolog_root, 'fakeembedded.pyx')])
    cython_util = Extension(name="emolog.cython_util", sources=[join(emolog_root, 'cython_util.pyx')])
    decoders = Extension(name="emolog.decoders", sources=[join(emolog_root, 'decoders.pyx')])
    cython_install_requires = [
        'Cython(>=0.27.3)',
    ]
    cython_setup_requires = [
        'Cython(>=0.27.3)',
    ]
else:
    cylib_sources = [
        join(emolog_root, 'cylib.cpp'),
        join(emolog_root, 'protocol', 'emolog_protocol.cpp'),
    ]
    fakeembedded_sources = [join(emolog_root, 'fakeembedded.c')]
    cython_util_sources = [join(emolog_root, 'cython_util.c')]
    decoders_sources = [join(emolog_root, 'decoders.c')]
    sources = cylib_sources + fakeembedded_sources + cython_util_sources + decoders_sources
    if not all([path.exists(x) for x in sources]):
        print("error: no cython but no c/c++ sources either")
        raise SystemExit
    cylib = Extension(name="emolog.cylib",
                      sources=cylib_sources,
                      include_dirs=[join(emolog_root, 'protocol')] + [numpy.get_include()],
                      define_macros=macros,
                      language="c++",
                      #data=[join('emolog', 'protocol', 'emolog_protocol.h')]
                      )
    fakeembedded = Extension(name="emolog.fakeembedded", sources=fakeembedded_sources)
    cython_util = Extension(name="emolog.cython_util", sources=cython_util_sources)
    decoders = Extension(name="emolog.decoders", sources=decoders_sources)
    cython_setup_requires = cython_install_requires = []

cython_extensions = [cylib, fakeembedded, cython_util, decoders]

setup(
    name='emolog',
    description='Command & Control side for emolog protocol',
    version='.'.join(map(str, VERSION)),
    setup_requires=[
        'setuptools>=18.0', # cython extensions
        'numpy'
    ] + cython_setup_requires,
    install_requires=[
        'pyelftools(==0.24)',
        'xlrd(==1.1.0)',
        'XlsxWriter(==1.1.5)',
        'pandas(==0.23.4)',
        'pyserial(>=3.2.1)',
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
            'emotool-vars = emolog.varsfile:main',
            'emotool-dwarf = emolog.dwarfutil:main',
            'emotool-dwarf-dump = emolog.dwarfutil:main_dump',
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
