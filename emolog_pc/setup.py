from setuptools import setup, Extension

from Cython.Build import cythonize

from emolog.setup import build_artifacts

# TODO - turn this into setup commands so it happens during setup (for instance not when run with --help)
artifacts = build_artifacts()

gdb_debug = False
macros = [] #[('CYTHON_TRACE', 1)]

cylib = Extension(name="emolog.cylib",
                  sources=["emolog/cylib.pyx", "../emolog_protocol/source/emolog_protocol.cpp"],
                  include_dirs=['../emolog_protocol/source'],
                  define_macros=macros,
                  language="c++")
cython_util = Extension(name="emolog.cython_util", sources=["emolog/cython_util.pyx"])

cython_extensions = [cylib, cython_util]

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
        'Cython(==0.27.3)',
        'pyserial(==3.2.1)',
        'pyserial-asyncio(==0.2)',
        'cx-Freeze(==5.0.2)',
    ],
    packages=['emolog', 'emolog.dwarf', 'emolog.emotool'],
    package_data={'emolog': artifacts},
    ext_modules = cythonize(cython_extensions, gdb_debug=gdb_debug),
    data_files=[('etc/emolog', ['local_machine_config.ini.example'])],
    entry_points={
        'console_scripts': [
            'emotool = emolog.emotool.main:main',
            'summarize = emolog.emotool.summarize:main'
        ]
    }
)
