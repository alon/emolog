@echo off
copy /b emolog.dll +,, > nul
set PYTHONPATH=.
python bin\emotool.py --baud 8000000 --hw_flow_control --elf ..\..\pump_drive\Release\pump_drive_tiva.out --snapshotfile snapshot_vars.csv --varfile vars.csv --runtime 3.0 --no_processing %1 %2 %3 %4 %5 %6
