import sys,shutil,subprocess,json
from pathlib import Path
from importlib import metadata
from concurrent.futures import ThreadPoolExecutor
import httpx
from PIL import Image,ImageDraw
root=Path(__file__).resolve().parent.parent;licenses=root/'licenses';licenses.mkdir(exist_ok=True)
image=Image.new('RGBA',(256,256),(0,0,0,0));draw=ImageDraw.Draw(image)
draw.rounded_rectangle((8,8,248,248),radius=50,fill='#2B4F89')
draw.rounded_rectangle((47,48,210,179),radius=24,fill='white');draw.polygon([(71,165),(71,212),(118,174)],fill='white')
for y,w in [(85,99),(113,79),(141,112)]:draw.rounded_rectangle((76,y,76+w,y+12),radius=5,fill='#2B4F89')
image.save(root/'animedialog/assets/app.ico',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
image.save(root/'animedialog/assets/app.png')
packages=['PySide6','PySide6_Essentials','PySide6_Addons','shiboken6','sherpa-onnx','rapidocr-onnxruntime','onnxruntime','numpy','opencv-python','soundfile','python-docx','lxml','httpx','httpcore','anyio','certifi','idna','cffi','shapely','PyYAML','Pillow']
for name in packages:
    try:dist=metadata.distribution(name)
    except metadata.PackageNotFoundError:continue
    for file in dist.files or []:
        if ('dist-info' in str(file)) and any(k in str(file).upper() for k in ['LICENSE','COPYING','NOTICE']):
            source=dist.locate_file(file)
            if source.is_file():
                target=licenses/name/Path(str(file).split('dist-info/',1)[-1]);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    (licenses/(name+'-version.txt')).write_text(dist.version,encoding='utf8')
urls={
 'whisper-MIT.txt':'https://raw.githubusercontent.com/ggml-org/whisper.cpp/master/LICENSE',
 'llama-MIT.txt':'https://raw.githubusercontent.com/ggml-org/llama.cpp/master/LICENSE',
 'Qt-LGPL-3.0.txt':'https://raw.githubusercontent.com/qt/qtbase/dev/LICENSES/LGPL-3.0-only.txt',
 'Qt-GPL-3.0.txt':'https://raw.githubusercontent.com/qt/qtbase/dev/LICENSES/GPL-3.0-only.txt',
 'FFmpeg-GPL-3.0.txt':'https://raw.githubusercontent.com/FFmpeg/FFmpeg/master/COPYING.GPLv3',
 'Python-LICENSE.txt':'https://raw.githubusercontent.com/python/cpython/3.12/LICENSE',
}
def fetch(item):
    name,url=item;r=httpx.get(url,follow_redirects=True,timeout=45);r.raise_for_status();(licenses/name).write_bytes(r.content)
with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(fetch,urls.items()))
r=subprocess.run([str(root/'vendor/ffmpeg.exe'),'-version'],capture_output=True,creationflags=0x08000000)
(licenses/'ffmpeg-build.txt').write_bytes(r.stdout+r.stderr)
shutil.copyfile(root/'LICENSE',licenses/'AnimeDialog-MIT.txt')
if (root/'vendor/llama/release.json').exists():shutil.copyfile(root/'vendor/llama/release.json',licenses/'llama-release.json')
source_url='https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz'
try:
    response=httpx.get(source_url,follow_redirects=True,timeout=90);response.raise_for_status();(licenses/'ffmpeg-9.0.2.tar.xz').write_bytes(response.content)
except httpx.HTTPError as e:print('FFmpeg source archive unavailable:',e,flush=True)
(licenses/'source-links.json').write_text(json.dumps(dict(ffmpeg=source_url,ffmpeg_build_scripts='https://github.com/GyanD/codexffmpeg',whisper='https://github.com/ggml-org/whisper.cpp',llama='https://github.com/ggml-org/llama.cpp'),indent=2),encoding='utf8')
print('Release assets and licenses ready',flush=True)
