from pathlib import Path
path=Path(__file__).resolve().parent.parent/'animedialog/assets/review.html'
text=path.read_text(encoding='utf8')
changes=[
 ('<select data-field="person">','<select data-field="person" data-current="${r.character_ids.length===1&amp;&amp;!r.turns.length?r.character_ids[0]:\'\'}">'),
 ("if(who){r.character_ids=[who];r.turns=[];}else if(r.turns.length)","if(who!==field('person').dataset.current){r.character_ids=who?[who]:[];r.turns=[];}else if(r.turns.length)"),
 ("else r.character_ids=[];r.speaker_review=", "r.speaker_review="),
 ("field('speaker_review').checked&&r.character_ids.length&&(!r.turns.length||r.turns.every(t=>t.character_id))", "field('speaker_review').checked&&(r.character_ids.length===1||r.turns.length&&r.turns.every(t=>t.character_id))"),
 ("r.evidence=['HTML人工修改人物归属'];", "r.evidence=[...new Set([...r.evidence,'HTML人工修改，请结合文字与人物审核状态核对'])];"),
 ("if($('group').checked)rows.sort((a,b)=>role(a).localeCompare(role(b),'zh-CN')||a.start_ms-b.start_ms);", "if($('group').checked)rows.sort((a,b)=>role(a).localeCompare(role(b),'zh-CN')||a.start_ms-b.start_ms);let priorGroup='';"),
 ("rows.map(r=>`<article", "rows.map(r=>`${$('group').checked&&priorGroup!==role(r)?'<h2>'+esc(priorGroup=role(r))+'</h2>':''}<article"),
]
for before,after in changes:
    if before in text:text=text.replace(before,after)
    elif after not in text:raise RuntimeError('Template fragment not found: '+before)
# JS expressions in a template literal use real &&, not HTML entities.
text=text.replace('r.character_ids.length===1&amp;&amp;!r.turns.length','r.character_ids.length===1&&!r.turns.length')
old="const k=role(r);if(!groups.has(k))groups.set(k,[]);groups.get(k).push(`[${time(r.start_ms)}] 原文：${r.original}\\n中文：${r.translation}\\n人物：${r.speaker_review==='confirmed'?'已确认':'待复核'}；文字：${r.text_review==='confirmed'?'已校对':'待校对'}`);"
new="const parts=r.turns.length?[...new Set(r.turns.map(t=>t.character_id))].map(cid=>({name:names.get(cid)||'待确认',zh:r.turns.filter(t=>t.character_id===cid).map(t=>t.text).join('\\n'),note:'整段原文含其他人物，分句时间留空时使用整段定位。'})):[{name:role(r),zh:r.translation,note:''}];for(const part of parts){const k=part.name;if(!groups.has(k))groups.set(k,[]);groups.get(k).push(`[${time(r.start_ms)}] 原文：${r.original}\\n中文：${part.zh}\\n人物：${r.speaker_review==='confirmed'?'已确认':'待复核'}；文字：${r.text_review==='confirmed'?'已校对':'待校对'}\\n${part.note}`);}"
if old in text:text=text.replace(old,new)
elif new not in text:raise RuntimeError('TXT fragment not found')
path.write_text(text,encoding='utf8')
