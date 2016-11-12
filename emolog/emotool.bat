copy /b emolog.dll +,,
python emotool.py --serial COM45 --elf ..\..\pump_drive_tiva\debug\pump_drive_tiva.out --varfile vars.csv --verbose --runtime 1.0 > out.log  2>&1
