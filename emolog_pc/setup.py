#!/usr/bin/env python3
from setuptools import setup, Extension

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
    def cythonize(*args, **kw):
        return None

gdb_debug = False
#macros = [('CYTHON_TRACE', 1)]
macros = []

# TODO - line tracing. compiler_directives no longer used
#                   compiler_directives={'linetrace': True, 'binding': True},
# gives
# extension.py:131: UserWarning: Unknown Extension options: 'compiler_directives'

cylib = Extension(name="emolog.cylib",
                  sources=["emolog/cylib.pyx", "../emolog_protocol/emolog_protocol.cpp"],
                  include_dirs=['../emolog_protocol'] + [numpy.get_include()],
                  define_macros=macros,
                  language="c++")
fakeembedded = Extension(name="emolog.fakeembedded", sources=["emolog/fakeembedded.pyx"])
cython_util = Extension(name="emolog.cython_util", sources=["emolog/cython_util.pyx"])
decoders = Extension(name="emolog.decoders", sources=["emolog/decoders.pyx"])

cython_extensions = [cylib, fakeembedded, cython_util, decoders]

setup(
    name='emolog',
    description='Command & Control side for emolog protocol',
    version="0.1",
    setup_requires=[
        'setuptools>=18.0', # cython extensions
        'cython>=0.27.3',
        'numpy'
    ],
    install_requires=[
        'pyelftools(==0.24)',
        'xlrd(==1.1.0)',
        'XlsxWriter(==1.0.2)',
        'pandas(==0.21.0)',
        'Cython(==0.27.3)',
        'pyserial(==3.2.1)',
        'pyserial-asyncio(==0.2)',
        'PyInstaller(==3.3)',
        'psutil(==5.4.1)',
        'colorama>=0.3.7',
    ],
    packages=['emolog', 'emolog.dwarf', 'emolog.emotool'],
    ext_modules = cythonize(cython_extensions, gdb_debug=gdb_debug),
    data_files=[('etc/emolog', ['config/local_machine_config.ini.example'])],
    entry_points={
        'console_scripts': [
            'emotool = emolog.emotool.main:main',
            'emogui = emolog.emotool.main_window:main',
            'summarize = emolog.emotool.summarize:main [summarize]'
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
