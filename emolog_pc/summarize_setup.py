from cx_Freeze import setup, Executable

# Dependencies are automatically detected, but it might need
# fine tuning.
buildOptions = dict(packages = [], excludes = [])

import sys
base = 'Win32GUI' if sys.platform=='win32' else None

executables = [
    Executable('summarize.py', base=base)
]

setup(name='summarize',
      version = '1.0',
      description = 'summarize emolog spreadsheets',
      options = dict(build_exe = buildOptions),
      executables = executables)
