Installation instructions for windows 8
=======================================

steps
1. python 3.5.2 64 bits
for all users, c:\python35, add to path, (install debug symbols - not required)
2. git 2.10.2-64
checkout as is, commit as is.
3. install code composer 6.2.0
default: c:\ti
choose C2000 all (include gcc)
choose arm all (include gcc)
choose all debuggers except blackhawk
choose gui composer (but not EVE)
4. install tivaware 2.1.3.156
5. open git bash at C:\Comet-ME Pump Drive\firmware; git clone https://github.com/alon/emolog.git
6. pip install -r requirements.txt
7. msys2 64bit && pacman -S pacman && pacman -Sy
8. pacman -S make
# installing gcc results in msys2.dll dependency (msys2.dll is a fork of cygwin1.dll)
9. pacman -S mingw-w64-x86_64-toolchain
10.0 in msys bash:
export PATH=/mingw64/bin:$PATH
make
# verify
ldd emolog.dll
        ntdll.dll => /c/WINDOWS/SYSTEM32/ntdll.dll (0x7ff8a80a0000)
        KERNEL32.DLL => /c/WINDOWS/System32/KERNEL32.DLL (0x7ff8a5ca0000)
        KERNELBASE.dll => /c/WINDOWS/System32/KERNELBASE.dll (0x7ff8a4b70000)
        msvcrt.dll => /c/WINDOWS/System32/msvcrt.dll (0x7ff8a7690000)
        USER32.dll => /c/WINDOWS/System32/USER32.dll (0x7ff8a7520000)
        win32u.dll => /c/WINDOWS/System32/win32u.dll (0x7ff8a4590000)
        GDI32.dll => /c/WINDOWS/System32/GDI32.dll (0x7ff8a5c50000)
        gdi32full.dll => /c/WINDOWS/System32/gdi32full.dll (0x7ff8a4890000)
        IMM32.DLL => /c/WINDOWS/System32/IMM32.DLL (0x7ff8a7730000)

and most importantly, it should not contain msys2.dll

11. open cmd
12. cd emolog
13. python emotool.py
14. connect FTDI FT2232H device
turn off "Serial Enumerator" at device-manager->com ports->com X->Properties->Advanced settings
15. Install drivers from FTDI: 

#### Debugging 
10. dependency walker