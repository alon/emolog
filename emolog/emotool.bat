@copy /b emolog.dll +,,
python emotool.py --serial COM7 --baud 8000000 --elf ..\..\pump_drive_tiva\Debug\pump_drive_tiva.out --varfile vars.csv --runtime 1.0 %1 %2 %3 %4 %5 %6
