@echo off
copy /b emolog.dll +,, > nul
python -mcProfile emotool.py --baud 8000000 --elf ..\..\pump_drive\Release\pump_drive_tiva.out --varfile vars.csv --runtime 0.5 %1 %2 %3 %4 %5 %6
