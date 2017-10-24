from distutils.core import setup
from Cython.Build import cythonize

setup(
  name = 'cython helpers',
  ext_modules = cythonize("cython_util.pyx"),
)
