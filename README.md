Installation instructions for windows 8
=======================================

Steps to install Emolog on a windows machine (tested on Windows 8)

1. Install python 3.5.x 64 bits
	for all users, folder should be c:\python35, add to path, (install debug symbols - not required)
2. install Git Extensions from github (it also installs git)
3. install TI Code Composer.
use default folder: c:\ti
(optional: for EVB) choose C2000 all (include gcc) 
choose arm all (include gcc)
choose all debuggers except blackhawk
choose gui composer (but not EVE)
4. git clone https://github.com/alon/emolog.git
5. pip install -r requirements.txt

The following is needed if a C compiler and 'make' utility are not available in the system:
6. install msys2 64bit 
7. in msys bash:
pacman -S pacman
pacman -Sy
pacman -S make
pacman -S mingw-w64-x86_64-toolchain
8. add "c:\msys64\mingw64\bin" and "c:\msys64\usr\bin" to the windows path
to verify that the code can build the C DLL:
open a command prompt at the emolog/emolog folder
make
emolog.dll should be created.
check that it doesn't have a superflous dependency:
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

9. open command prompt at the emolog\emolog folder
10. Install FTDI drivers
11. connect FTDI FT2232H device
12. turn off "Serial Enumerator" at device-manager->com ports->com X->Properties->Advanced settings
13. run emotool.bat
