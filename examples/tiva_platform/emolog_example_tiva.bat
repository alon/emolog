@echo off
copy /b emolog.dll +,, > nul
python ..\..\emolog_pc\emotool.py --serial COM42 --baud 1000000 --elf Debug\emolog_example_client.out --varfile ..\examples_common\example_vars.csv --runtime 3.0 --ticks-per-second 200 %1 %2 %3 %4 %5 %6
