pyinstaller emotool.spec --noconfirm
pyinstaller "..\..\..\emolog_work\post_processor.py"
copy "..\..\..\emolog_work\for pyInstaller\emolog.bat" dist
copy "..\..\..\emolog_work\for pyInstaller\local_machine_config.ini" dist
copy "..\..\..\emolog_work\vars.csv" dist\emotool
copy "..\..\..\emolog_work\snapshot_vars.csv" dist\emotool
md dist\Outputs
