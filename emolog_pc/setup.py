from distutils.core import setup
from Cython.Build import cythonize

setup(
    name = 'Emotool',
    description='Command & Control side for emolog protocol',

    ext_modules = cythonize("cython_util.pyx"),
)
