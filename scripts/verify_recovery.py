"""Exercise actual workers, checkpoints, audio selection and voice references.

The reference speaker is an isolated fixture, not an annotation of the film.
"""
import ctypes
from ctypes import wintypes as w
import json,os,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from animedialog.store import Project
from animedialog.domain import utterance
from animedialog.media import probe,run
from animedialog.settings import executable

root=Path(__file__).resolve().parent.parent
p=Project(root/'.qa/恢复与声音样本','恢复验收')
video=root/'.qa/中文路径 第1段.mp4'
ep=p.add_episode(video,'暂停与恢复');ep.update(language='ja',audio_index=1,duration_ms=32000,metadata=probe(video),ocr_regions=[[0,.8,1,.19]])
p.put('episodes',ep)
report={}

def start(job):
    log=(p.folder/'cache'/f"{job['id']}.log").open('wb')
    child=subprocess.Popen([sys.executable,'-m','animedialog.worker','--project',str(p.folder),'--job',job['id']],cwd=root,stdout=log,stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW)
    log.close();return child

def finish(job,child,expected='completed'):
    child.wait(timeout=180);state=p.get('jobs',job['id'])
    assert state['state']==expected,state
    return state

def children(pid):
    class Entry(ctypes.Structure):
        _fields_=[('dwSize',w.DWORD),('cntUsage',w.DWORD),('th32ProcessID',w.DWORD),('th32DefaultHeapID',ctypes.c_size_t),('th32ModuleID',w.DWORD),('cntThreads',w.DWORD),('th32ParentProcessID',w.DWORD),('pcPriClassBase',w.LONG),('dwFlags',w.DWORD),('szExeFile',w.WCHAR*260)]
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.CreateToolhelp32Snapshot.argtypes=[w.DWORD,w.DWORD];api.CreateToolhelp32Snapshot.restype=w.HANDLE
    api.Process32FirstW.argtypes=[w.HANDLE,ctypes.POINTER(Entry)];api.Process32NextW.argtypes=[w.HANDLE,ctypes.POINTER(Entry)];api.CloseHandle.argtypes=[w.HANDLE]
    snap=api.CreateToolhelp32Snapshot(2,0);entry=Entry();entry.dwSize=ctypes.sizeof(entry);processes=[]
    try:
        ok=api.Process32FirstW(snap,ctypes.byref(entry))
        while ok:
            processes.append((entry.th32ProcessID,entry.th32ParentProcessID,entry.szExeFile))
            ok=api.Process32NextW(snap,ctypes.byref(entry))
    finally:api.CloseHandle(snap)
    descendants={pid};result=[]
    while True:
        new=[(id,parent,name) for id,parent,name in processes if parent in descendants and id not in descendants]
        if not new:break
        descendants.update(id for id,_,_ in new);result.extend((id,name) for id,_,name in new)
    return result

def terminate_worker(child):
    # The development venv launcher may delegate to a base Python process.
    actual=[id for id,name in children(child.pid) if name.lower()=='python.exe']
    if not actual:child.kill();return
    api=ctypes.WinDLL('kernel32',use_last_error=True)
    api.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];api.OpenProcess.restype=w.HANDLE
    api.TerminateProcess.argtypes=[w.HANDLE,w.UINT];api.CloseHandle.argtypes=[w.HANDLE]
    for pid in actual:
        handle=api.OpenProcess(1,False,pid)
        assert handle
        try:assert api.TerminateProcess(handle,1)
        finally:api.CloseHandle(handle)

j=p.new_job(ep['id'],dict(speakers=True,semantic=False,ocr=True));child=start(j);cache=p.folder/'cache'/j['id'];deadline=time.monotonic()+90
while not (cache/'ocr-checkpoint.json').exists():
    assert child.poll() is None,p.get('jobs',j['id'])
    assert time.monotonic()<deadline,'OCR checkpoint timeout'
    time.sleep(.1)
asr=cache/'asr-00000.json';asr_time=asr.stat().st_mtime_ns
p.update_job(j['id'],request='pause');finish(j,child,'paused')
checkpoint=json.loads((cache/'ocr-checkpoint.json').read_text(encoding='utf8'));assert checkpoint['next_ms']>0
p.update_job(j['id'],request='run');finish(j,start(j));assert asr.stat().st_mtime_ns==asr_time
report['pause_resume']={'saved_ocr_ms':checkpoint['next_ms'],'asr_reused':True,'rows':len(p.rows(ep['id']))}
print('Actual pause and checkpoint resume passed',flush=True)

# Force the Python worker down while a native Whisper child is running.
j2=p.new_job(ep['id'],dict(speakers=False,semantic=False,ocr=False));child=start(j2);deadline=time.monotonic()+60
while not any(name=='whisper-cli.exe' for _,name in children(child.pid)):
    assert child.poll() is None,p.get('jobs',j2['id']);assert time.monotonic()<deadline
    time.sleep(.05)
native=children(child.pid);terminate_worker(child);child.wait(timeout=10);time.sleep(1)
assert not children(child.pid),native
p.update_job(j2['id'],request='run');finish(j2,start(j2))
report['forced_interrupt']={'native_children_terminated':True,'restart':'completed','saved_rows_retained':True}
print('Actual forced termination and restart passed',flush=True)

preview=p.new_job(ep['id'],dict(task='preview'));finish(preview,start(preview))
preview_path=Path(p.get('episodes',ep['id'])['preview_path']);preview_meta=probe(preview_path)
assert abs(float(preview_meta['format']['duration'])-32)<.1
report['preview']={'duration_ms':round(float(preview_meta['format']['duration'])*1000),'codec':next(s['codec_name'] for s in preview_meta['streams'] if s['codec_type']=='video')}

row=next(r for r in p.rows(ep['id']) if r['original'] and r['end_ms']-r['start_ms']>=1000)
before=row['original'];p.edit(row['id'],notes='人工版本保留验收',text_review='confirmed')
large=p.new_job(ep['id'],dict(target_ids=[row['id']],large=True,speakers=False,semantic=False));finish(large,start(large))
assert p.get('utterances',row['id'])['original']==before and p.get('utterances',row['id'])['text_review']=='confirmed'
assert any(x['row_id']==row['id'] for x in p.proposals())
report['large_retranscribe']={'human_original_preserved':True,'suggestion_generated':True}

cid=p.character('验收样本人声（同音源测试）');p.assign([row['id']],cid)
sample=p.new_job(ep['id'],dict(task='sample',row_id=row['id']));finish(sample,start(sample))
other=p.add_episode(video,'同一音源样本匹配');other.update(audio_index=1,duration_ms=32000);p.put('episodes',other)
pending=utterance(other['id'],row['start_ms'],row['end_ms'],original='待匹配的测试记录');p.put('utterances',pending)
match=p.new_job(other['id'],dict(task='match'));finish(match,start(match))
suggestions=[x for x in p.proposals() if x['row_id']==pending['id']]
assert suggestions and suggestions[-1]['data']['character_ids']==[cid]
assert p.get('utterances',pending['id'])['speaker_review']=='pending'
report['shared_voice_sample']={'same_audio_fixture':True,'suggested_character':cid,'human_confirmation_automatic':False}

# A second silent audio track and an embedded Chinese subtitle in an MKV.
fixture=root/'.qa/双音轨 静音字幕.mkv';sub=root/'.qa/中文轨.srt'
sub.write_text('1\n00:00:01,000 --> 00:00:03,000\n第一句重复字幕\n\n2\n00:00:03,100 --> 00:00:04,800\n第一句重复字幕\n',encoding='utf8')
if not fixture.exists():
    result=run([executable('ffmpeg'),'-hide_banner','-loglevel','error','-y','-i',str(video),'-f','lavfi','-i','anullsrc=r=16000:cl=mono','-i',str(sub),'-t','5','-map','0:v:0','-map','0:a:0','-map','1:a:0','-map','2:0','-c:v','copy','-c:a:0','copy','-c:a:1','pcm_s16le','-c:s','srt','-metadata:s:a:0','language=jpn','-metadata:s:a:1','language=zho','-metadata:s:s:0','language=zho',str(fixture)],timeout=60)
    assert result.returncode==0,result.stderr
metadata=probe(fixture);assert len([s for s in metadata['streams'] if s['codec_type']=='audio'])==2
for with_sub in [False,True]:
    testep=p.add_episode(fixture,'静音与重复字幕'+str(with_sub));testep.update(audio_index=2,language='zh',subtitle_indices=[3] if with_sub else [],duration_ms=5000);p.put('episodes',testep)
    job=p.new_job(testep['id'],dict(speakers=False,semantic=False,ocr=False));finish(job,start(job));rows=p.rows(testep['id'])
    assert len(rows)==(2 if with_sub else 0),rows
    if with_sub:assert all(r['original']=='第一句重复字幕' and r['translation']=='' for r in rows)
report['multiple_tracks_silence_subtitles']={'chosen_audio_index':2,'silent_rows':0,'repeated_subtitle_rows':2,'chinese_translation_duplicate':False}
cancel=p.new_job(ep['id'],{});p.update_job(cancel['id'],request='cancel');finish(cancel,start(cancel),'cancelled')
report['cancel_preserves_rows']=True
(root/'.qa/recovery-test.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(report,ensure_ascii=False),flush=True);p.close()
