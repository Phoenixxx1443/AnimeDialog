import sys,subprocess,json,time,os
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from animedialog.store import Project
root=Path(__file__).resolve().parent.parent;p=Project(root/'.qa/独立程序验收');e=p.add_episode(root/'.qa/中文路径 第1段.mp4','独立程序实际视频验收')
e.update(language='ja',audio_index=1,duration_ms=32000,ocr_regions=[[0,.80,1,.19]]);p.put('episodes',e)
job=p.new_job(e['id'],dict(speakers=True,semantic=True,ocr=True));folder=p.folder;p.close()
exe=Path(sys.argv[1]) if len(sys.argv)>1 else root/'dist/AnimeDialog/AnimeDialog.exe'
env=dict(os.environ);env['PATH']=str(Path(os.environ['WINDIR'])/'System32')+';'+os.environ['WINDIR']
started=time.monotonic()
result=subprocess.run([str(exe.resolve()),'--worker','--project',str(folder),'--job',job['id']],env=env,timeout=240,capture_output=True)
p=Project(folder);state=p.get('jobs',job['id']);assert result.returncode==0,(result.returncode,result.stderr);assert state['state']=='completed',state
rows=p.rows(e['id']);assert rows and all(r['machine']['initial']['original']==r['original'] for r in rows)
report=dict(executable=str(exe.resolve()),path=env['PATH'],exit_code=result.returncode,state=state['state'],seconds=round(time.monotonic()-started,2),python_path_required=False,records=len(rows),machine_versions_separate=True)
(root/'.qa/frozen-test.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(report,ensure_ascii=False));p.close()
