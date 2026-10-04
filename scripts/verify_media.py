"""Real-engine integration run using two excerpts; not a two-episode accuracy benchmark."""
import sys,json,time,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from animedialog.settings import executable
from animedialog.media import run,probe
from animedialog.store import Project
from animedialog.pipeline import process_job
root=Path(__file__).resolve().parent.parent;qa=root/'.qa';qa.mkdir(exist_ok=True)
video=Path(r'D:\steam\steamapps\workshop\content\431960\3662337997\超时空辉夜姬4K60fps.mp4')
p=Project(qa/'两段视频','实际片段验收');jobs=[]
for i,start in enumerate([380,410]):
    clip=qa/f'中文路径 第{i+1}段.mp4'
    if not clip.exists():
        result=run([executable('ffmpeg'),'-hide_banner','-loglevel','error','-y','-ss',str(start),'-i',str(video),'-t','32','-map','0:v:0','-map','0:a:0','-vf','scale=960:-2,fps=25','-c:v','libx264','-preset','veryfast','-crf','24','-c:a','aac','-movflags','+faststart',str(clip)],timeout=180)
        if result.returncode:raise RuntimeError(result.stderr.decode('utf8',errors='replace'))
    ep=next((e for e in p.episodes() if e['path']==str(clip)),None) or p.add_episode(clip,f'验收片段 {i+1}')
    metadata=probe(clip);ep.update(metadata=metadata,language='ja',duration_ms=32000,audio_index=1,ocr_regions=[[0,.80,1,.19]])
    p.put('episodes',ep)
    job=next((j for j in p.all('jobs') if j['episode_id']==ep['id']),None) or p.new_job(ep['id'],dict(speakers=True,semantic=True,ocr=True))
    jobs.append(job['id'])
folder=p.folder;p.close();started=time.monotonic()
for id in jobs:
    q=Project(folder);j=q.get('jobs',id)
    if j['state']=='completed':q.close();continue
    q.update_job(id,request='run');q.close()
    if process_job(folder,id):raise RuntimeError('Real pipeline failed: '+id)
p=Project(folder);report=dict(seconds=round(time.monotonic()-started,1),rows=len(p.rows()),characters=len(p.characters()),jobs=[p.get('jobs',id) for id in jobs])
(qa/'real-media.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(report,ensure_ascii=False));p.close()
