import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from animedialog.store import Project
from animedialog.exporters import export_docx,export_html,export_txt,export_srt,export_json
from animedialog.importers import read_transcript
root=Path(__file__).resolve().parent.parent;qa=root/'.qa';qa.mkdir(exist_ok=True)
p=Project(root/'作品/超时空辉夜姬');rows=p.rows()
export_docx(p,rows[60:72],qa/'排版检查.docx',False)
out=p.folder/'导出';out.mkdir(exist_ok=True)
export_html(p,rows,out/'超时空辉夜姬_AnimeDialog离线审核.html',True)
export_txt(p,rows,out/'超时空辉夜姬_人物分类.txt',True)
export_srt(p,rows,qa/'全片时间轴.srt')
export_json(p,rows,qa/'全片回导.json')
assert len(read_transcript(out/'超时空辉夜姬_AnimeDialog离线审核.html')['rows'])==1694
assert len(read_transcript(qa/'全片回导.json')['rows'])==1694
p.close()
p=Project(qa/'两段视频');export_html(p,p.rows(),qa/'离线审核.html',True);p.close()
print('DOCX, HTML, TXT, SRT, JSON exports created and records checked')
