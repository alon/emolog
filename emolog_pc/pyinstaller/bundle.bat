pyinstaller emotool.spec --noconfirm
pyinstaller "..\..\..\emolog_work\post_processor.py"
copy "..\..\..\emolog_work\for pyInstaller\emolog.bat" dist
copy "..\..\..\emolog_work\for pyInstaller\local_machine_config.ini" dist
md dist\Outputs

:: TEMP
copy "..\..\..\Debug\BQ2.0.elf" dist

