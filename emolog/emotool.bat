copy /b emolog.dll +,,
python emotool.py --serial COM34 --elf ..\protocol_embedded\debug\protocol_embedded.out --var sine,float,1,0 --var sawtooth,int,1,0 --verbose >> out.log  2>&1