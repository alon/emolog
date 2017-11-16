import pstats, cProfile
import sys

from emolog.emotool.main import main

sys.argv = ['prof.py', '--fake', '--runtime', '10']

cProfile.runctx("main()", globals(), locals(), "prof.prof")

s = pstats.Stats("prof.prof")
s.strip_dirs().sort_stats("time").print_stats(40)
