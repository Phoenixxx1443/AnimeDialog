// Pure DOM/event tests for our template. No browser, video or filesystem navigation.
const fs=require('node:fs');const path=require('node:path');const assert=require('node:assert/strict');
const {JSDOM,VirtualConsole}=require('../.runtime/html-test/node_modules/jsdom');
const root=path.resolve(__dirname,'..');const file=path.join(root,'.qa','离线审核.html');
const template=fs.readFileSync(file,'utf8');const errors=[];const downloads=[];const blobs=new Map();let serial=0;
const dom=new JSDOM(template,{runScripts:'dangerously',url:'https://animedialog.test/',virtualConsole:new VirtualConsole().on('jsdomError',e=>errors.push(e.message)),beforeParse(window){
    window.structuredClone=structuredClone;
    window.Blob=Blob;window.URL.createObjectURL=blob=>{const u='blob:test-'+(++serial);blobs.set(u,blob);return u;};window.URL.revokeObjectURL=()=>{};
    window.HTMLAnchorElement.prototype.click=function(){downloads.push({name:this.download,href:this.href});};
}});
const {window}=dom;const doc=window.document;
assert.equal(errors.length,0,errors.join('\n'));assert.equal(doc.querySelectorAll('article.row').length,17);
assert.ok(doc.querySelectorAll('h2').length>1,'Grouped headers render');
const record=doc.querySelector('article.row');const summary=record.querySelector('summary');summary.click();
const select=record.querySelector('[data-field="person"]');select.value=select.options[2].value;
record.querySelector('[data-field="speaker_review"]').checked=true;
record.querySelector('[data-field="text_review"]').checked=false;
record.querySelector('[data-field="notes"]').value='DOM 回导验证';record.querySelector('[data-apply]').click();
const cache=JSON.parse(window.localStorage.getItem(window.localStorage.key(0)));const saved=cache[record.dataset.id];
assert.equal(saved.character_ids.length,1);assert.equal(saved.speaker_review,'confirmed');assert.equal(saved.text_review,'pending');assert.equal(saved.notes,'DOM 回导验证');
const next=doc.querySelector('article[data-id="'+record.dataset.id+'"]');assert.ok(next.textContent.includes('人物已确认 / 文字待校对'));
doc.querySelector('#search').value='不存在的字符串';doc.querySelector('#search').dispatchEvent(new window.Event('input'));assert.equal(doc.querySelectorAll('article.row').length,0);
doc.querySelector('#search').value='';doc.querySelector('#search').dispatchEvent(new window.Event('input'));
doc.querySelector('#save').click();assert.equal(downloads.at(-1).name,'AnimeDialog_人工核对.html');
assert.equal(errors.length,0,errors.join('\n'));
blobs.get(downloads.at(-1).href).text().then(text=>{fs.writeFileSync(path.join(root,'.qa','网页修改_回导验证.html'),text,'utf8');dom.window.close();console.log('HTML DOM events, grouping, assignment, separate reviews, autosave, search and saved HTML passed');});
