"""Reproducible vendor acquisition; use publisher release APIs and no shell execution."""
import io,json,shutil,zipfile
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parent.parent
def get(url):
    with httpx.Client(follow_redirects=True,timeout=180) as c:
        r=c.get(url);r.raise_for_status();return r.content
def releases(repo):return json.loads(get('https://api.github.com/repos/'+repo+'/releases?per_page=50'))
def unzip_binary(data,dest):
    dest.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for entry in z.infolist():
            if Path(entry.filename).suffix.lower() in ['.exe','.dll','.txt','.md']:
                target=dest/Path(entry.filename).name
                if not entry.is_dir():target.write_bytes(z.read(entry))
def main():
    vendor=ROOT/'vendor';vendor.mkdir(exist_ok=True)
    if not (vendor/'ffprobe.exe').exists():
        unzip_binary(get('https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'),vendor)
        print('FFmpeg installed',flush=True)
    for name,repo,needle in [('whisper','ggml-org/whisper.cpp','bin-x64'),('llama','ggml-org/llama.cpp','bin-win-vulkan-x64')]:
        dest=vendor/name
        if (dest/('whisper-cli.exe' if name=='whisper' else 'llama-server.exe')).exists():continue
        choices=[]
        for r in releases(repo):
            choices=[a for a in r['assets'] if needle in a['name'] and a['name'].endswith('.zip')]
            if name=='whisper':
                vulkan=[a for a in r['assets'] if 'vulkan' in a['name'].lower() and 'x64' in a['name'] and a['name'].endswith('.zip')]
                choices=vulkan or [a for a in choices if not any(t in a['name'] for t in ['cuda','cublas','blas'])]
            if choices:break
        if not choices:raise RuntimeError(f'{repo} has no matching Windows asset in recent releases')
        print(name,r['tag_name'],choices[0]['name'],flush=True)
        unzip_binary(get(choices[0]['browser_download_url']),dest)
        (dest/'release.json').write_text(json.dumps(dict(repository=repo,version=r['tag_name'],asset=choices[0]['name'])),encoding='utf8')
if __name__=='__main__':main()
