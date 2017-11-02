from setuptools import setup

from Cython.Build import cythonize

from emolog.setup import build_artifacts

# TODO - turn this into setup commands so it happens during setup (for instance not when run with --help)
artifacts = build_artifacts()

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
        'cx-Freeze(==5.0.2)',
    ],
    packages=['emolog', 'emolog.dwarf', 'emolog.emotool'],
    package_data={'emolog': artifacts},
    ext_modules = cythonize("emolog/cython_util.pyx"),
    data_files=[('etc/emolog', ['local_machine_config.ini.example'])],
    entry_points={
        'console_scripts': [
            'emotool = emolog.emotool.main:main',
            'summarize = emolog.emotool.summarize:main'
        ]
    }
)
