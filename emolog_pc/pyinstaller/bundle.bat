pyinstaller emotool.spec --noconfirm
copy "..\..\..\emolog_work\for pyInstaller\emolog.bat" dist
copy "..\..\..\emolog_work\for pyInstaller\local_machine_config.ini" dist
md dist\Outputs

:: TEMP
copy "..\..\..\Debug\BQ2.0.elf" dist

