# Build from the repository root: .venv\Scripts\pyinstaller AnimeDialog.spec --noconfirm
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files,collect_dynamic_libs
root=Path(SPECPATH)
datas=[(str(root/'animedialog/assets'),'animedialog/assets'),(str(root/'使用说明.html'),'.'),(str(root/'THIRD_PARTY_NOTICES.md'),'.'),(str(root/'licenses'),'licenses')]
datas+=collect_data_files('rapidocr_onnxruntime')
vendor=root/'vendor'
for name in ['ffmpeg.exe','ffprobe.exe']:
    datas.append((str(vendor/name),'vendor'))
for tool in ['whisper','llama']:
    for file in (vendor/tool).iterdir():
        if file.suffix.lower()=='.dll' or file.name in ['whisper-cli.exe','llama-server.exe','release.json']:
            datas.append((str(file),'vendor/'+tool))
binaries=collect_dynamic_libs('sherpa_onnx')
a=Analysis(['main.py'],pathex=[str(root)],binaries=binaries,datas=datas,
           hiddenimports=['sherpa_onnx','rapidocr_onnxruntime','onnxruntime','soundfile','docx'],
           hookspath=[],hooksconfig={},runtime_hooks=[],
           excludes=['tkinter','matplotlib','pandas','scipy','pytest','IPython','notebook','PySide6.QtWebEngineCore','PySide6.QtWebEngineWidgets','PySide6.QtWebEngineQuick','PySide6.QtQml','PySide6.QtQuick'],noarchive=False)
# Qt 6.11 on Windows uses the OS ICU API with unsuffixed exports. Dependency
# scanning can accidentally select Git's versioned ICU from the build PATH.
# Windows 11 supplies the matching system ICU; keep third-party ICU out of its way.
a.binaries=[entry for entry in a.binaries if not Path(entry[0]).name.lower().startswith(('icuuc','icuin','icudt'))]
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='AnimeDialog',debug=False,bootloader_ignore_signals=False,strip=False,upx=False,console=False,icon=str(root/'animedialog/assets/app.ico'),version=str(root/'scripts/windows_version.txt'))
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='AnimeDialog')
