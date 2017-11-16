import pstats, cProfile
import sys
import os

from emolog.emotool.main import main

sys.argv = ['python', os.path.join('pyinstaller', 'emotool.py'), '--fake', '--runtime', '10']

cProfile.runctx("main()", globals(), locals(), "prof.prof")

s = pstats.Stats("prof.prof")
s.strip_dirs().sort_stats("cumtime").print_stats(40)
