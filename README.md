[![Build status](https://ci.appveyor.com/api/projects/status/ucgxt3386bikt3s4/branch/master?svg=true)](https://ci.appveyor.com/project/alon/emolog/branch/master)

Emolog
======

Memory reading from processes.
Use case:
- Embedded C program
- PC
- RS422 connection
- Debug cycle:
  - compile ELF
  - produce log
  - analyze results

Emolog helps by providing:
- embeddable C implementation of embedded side of protocol
  - minimal functions to implement to integrate to your control loop:
  - examples for TI TIVA, STM32F3 and PC
- PC side ELF DWARF analyzer and logger:
  - emotool.py --vars variables.csv --elf output.elf --serial hwgrep://0403:6010 --runtime 1.0
  - produces CSV output easy to analyze
  - variables.csv is a simple format specifying rate (relative to clock)

Installation instructions for windows 8
=======================================

Steps to install Emolog on a windows machine (tested on Windows 8)

1. Install python 3.5.x 64 bits
	for all users, folder should be c:\python35, add to path, (install debug symbols - not required)
2. install Git Extensions from github (it also installs git)
3. Install Visual studio build tools (required by cython)
http://landinghub.visualstudio.com/visual-cpp-build-tools
4. install TI Code Composer.
use default folder: c:\ti
(optional: for EVB) choose C2000 all (include gcc) 
choose arm all (include gcc)
choose all debuggers except blackhawk
choose gui composer (but not EVE)
5. Install virtualenv globally (requires administrator privildges)
pip install virtualenv # or use your package manager
6. git clone https://github.com/alon/emolog.git
7. cd emolog_pc; // NB: You should create a virtualenv; The following will install packages globally!
8. create virtual environment
virtualenv venv
venv\scripts\activate
9. Install cython (setup.py depends on it, but also lists it as a dependency)
pip install cython
10. Install package for development including all requirements:
pip install -e .
11. open command prompt at the emolog\emolog folder
12. Install FTDI drivers
13. connect FTDI FT2232H device
14. turn off "Serial Enumerator" at device-manager->com ports->com X->Properties->Advanced settings
15. run emotool.bat

Development
===========

After any change to a pyx file you need to rebuild the cython extensions:
(venv)> python setup.py build_ext --inplace
