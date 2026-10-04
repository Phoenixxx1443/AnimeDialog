"""Import the prior transcript once, retaining all 1694 source records verbatim."""
import sys,json,collections
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from animedialog.store import Project
from animedialog.importers import import_transcript
from animedialog.media import probe
root=Path(__file__).resolve().parent.parent
old=Path(r'C:\Users\Administrator\Documents\Codex\2026-10-03\zhe\work\semantic_final_rows.json')
video=Path(r'D:\steam\steamapps\workshop\content\431960\3662337997\超时空辉夜姬4K60fps.mp4')
project=Project(root/'作品'/'超时空辉夜姬','超时空辉夜姬')
ep=next(iter(project.episodes()),None) or project.add_episode(video,'完整影片')
metadata=probe(video);ep.update(metadata=metadata,duration_ms=round(float(metadata['format']['duration'])*1000),language='ja',audio_index=next(s['index'] for s in metadata['streams'] if s['codec_type']=='audio'))
project.put('episodes',ep);print('import',import_transcript(project,old,ep['id']))
source=json.loads(old.read_text(encoding='utf8'));rows=project.rows()
assert len(rows)==len(source)==1694
lookup={str(r.get('id',i)):r for i,r in enumerate(source)}
assert all(lookup[r['legacy_id']]==r['machine'] for r in rows)
counts=collections.Counter(r['kind'] for r in rows);print('Verified',len(rows),counts)
report=dict(total=len(rows),categories=dict(counts),all_source_records_unchanged=True,
            candidate_confirmed_in_old_file=sum(bool(r.get('confirmed')) for r in source),human_confirmed=sum(r['speaker_review']=='confirmed' for r in rows))
(project.folder/'导入核验.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8');project.close()
