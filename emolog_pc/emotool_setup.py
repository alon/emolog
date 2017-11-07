from cx_Freeze import setup, Executable

from emolog.setup import get_artifacts

"""
Known problems:
resulting executable fails on linux. Since that is not the production
environment (which is windows), this is not a real problem at them moment.

Error:
(cd build/exe.linux-x86_64-3.6/; ./emotool)
Traceback (most recent call last):
  File "/home/hiro/tests/python/cxfreeze/venv/lib/python3.6/site-packages/cx_Freeze/initscripts/__startup__.py", line 14, in run
    module.run()
  File "/home/hiro/tests/python/cxfreeze/venv/lib/python3.6/site-packages/cx_Freeze/initscripts/Console.py", line 26, in run
    exec(code, m.__dict__)
  File "main.py", line 1, in <module>
  File "/home/hiro/tests/python/cxfreeze/venv/lib/python3.6/site-packages/pandas/__init__.py", line 23, in <module>
    from pandas.compat.numpy import *
  File "/home/hiro/tests/python/cxfreeze/venv/lib/python3.6/site-packages/pandas/compat/__init__.py", line 31, in <module>
    from distutils.version import LooseVersion
  File "/home/hiro/tests/python/cxfreeze/venv/lib64/python3.6/distutils/__init__.py", line 17, in <module>
    real_distutils = imp.load_module("_virtualenv_distutils", None, distutils_path, ('', '', imp.PKG_DIRECTORY))
  File "/home/hiro/tests/python/cxfreeze/venv/lib64/python3.6/imp.py", line 245, in load_module
    return load_package(name, filename)
  File "/home/hiro/tests/python/cxfreeze/venv/lib64/python3.6/imp.py", line 217, in load_package
    return _load(spec)
  File "<frozen importlib._bootstrap>", line 683, in _load
AttributeError: 'NoneType' object has no attribute 'name'

"""

# TODO - turn this into setup commands so it happens during setup (for instance not when run with --help)
artifacts = get_artifacts()

# Dependencies are automatically detected, but it might need
# fine tuning.
buildOptions = dict(packages = [
    'asyncio', 'emolog', 'numpy'],
    excludes = [])

base = 'Console'

executables = [
    Executable('emotool.py', base=base)
]

setup(name='emotool',
      version = '0.1',
      description = 'Emolog PC tool',
      options = dict(build_exe = buildOptions),
      executables = executables,
      )
