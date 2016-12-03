@echo off
copy /b emolog.dll +,, > nul
python emotool.py --baud 8000000 --elf ..\..\pump_drive_tiva\Debug\pump_drive_tiva.out --varfile vars.csv --runtime 1.0 %1 %2 %3 %4 %5 %6
