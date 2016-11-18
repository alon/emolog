copy /b emolog.dll +,,
python emotool.py --serial COM45 --baud 6000000 --elf ..\..\pump_drive_tiva\debug\pump_drive_tiva.out --varfile vars.csv --runtime 0.01 --silent --no-cleanup
