# -*- mode: python -*-

block_cipher = None


emotool_a = Analysis(['emotool.py'],
             pathex=['/images/cometme-wp/workspace/emolog_pc'],
             binaries=[],
             datas=[('../config/local_machine_config.ini.example', '.')],
             hiddenimports=['emolog', 'emolog.setup', 'emolog.emotool', 'emolog.emotool.embedded',
                            'pandas._libs.tslibs.timedeltas'],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher)

emotool_pyz = PYZ(emotool_a.pure, emotool_a.zipped_data,
             cipher=block_cipher)
emotool_exe = EXE(emotool_pyz,
          emotool_a.scripts,
          exclude_binaries=True,
          name='emotool',
          debug=False,
          strip=False,
          upx=True,
          console=True )
emotool_coll = COLLECT(emotool_exe,
               emotool_a.binaries,
               emotool_a.zipfiles,
               emotool_a.datas,
               strip=False,
               upx=True,
               name='emotool')

