'use strict';
const $ = (s, root = document) => root.querySelector(s);
let data, active, project = '', tab = 'finding', pending = null, dirty = false;
const questionBuffers = new Map();
let editorIssue=null, editorVersion=null;
const names = {};
const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const reviewStatus = i => i.review.approved && !i.review.stale ? 'selected' : i.review.draft ? 'draft' : 'unreviewed';
function notice(message, error = false) { const n = $('#notice'); if(!error){n.hidden=true;n.textContent='';return;} n.textContent = message; n.hidden = !message; n.setAttribute('role', error ? 'alert' : 'status'); }
async function api(url, body) {
  const response = await fetch(url, body ? {method:'POST', headers:{'Content-Type':'application/json','X-Review-Token':data.token},body:JSON.stringify(body)} : {});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'Request failed. Reload and retry.');
  return result;
}
// Deliberately small Markdown renderer: escape all raw HTML, never render remote resources.
function inline(text) {
  const fragments = [];
  let value = esc(text).replace(/`([^`]+)`/g, (_, code) => { fragments.push(`<code>${code}</code>`); return `\u0000${fragments.length - 1}\u0000`; });
  value = value.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  // Source paths remain visible rather than becoming unsupported file:// browser links.
  return value.replace(/\u0000(\d+)\u0000/g, (_, n) => fragments[Number(n)]);
}
function markdown(text) {
  const lines = text.split('\n'), output = []; let para = [], code = null, fence = null, list = false;
  const flush = () => { if (para.length) { output.push(`<p>${inline(para.join(' '))}</p>`); para = []; } if (list) { output.push('</ul>'); list = false; } };
  for (const line of lines) {
    const marker=line.match(/^ {0,3}(`{3,}|~{3,})(.*)$/);
    if(marker && code===null){flush();fence=marker[1];code=[];continue;}
    if(marker && code!==null && marker[1][0]===fence[0] && marker[1].length>=fence.length && !marker[2].trim()){output.push(`<pre><code>${esc(code.join('\n'))}</code></pre>`);code=null;fence=null;continue;}
    if (code !== null) {code.push(line); continue;}
    if (/^<!-- (?:Managed by issue-review\.|issue-desk:end )/.test(line)) continue;
    if (!line.trim()) {flush(); continue;}
    if (/^#{1,6}\s/.test(line)) {flush(); const level=Math.min(line.match(/^#+/)[0].length,6);output.push(`<h${level}>${inline(line.replace(/^#+\s/, ''))}</h${level}>`); continue;}
    if (/^\s*(?:[-*]|\d+\.)\s/.test(line)) { if (para.length) flush(); if (!list) {output.push('<ul>');list = true;} output.push(`<li>${inline(line.replace(/^\s*(?:[-*]|\d+\.)\s/, ''))}</li>`); continue; }
    if (list || (/^Solution:/.test(line) && para.length && /^Problem:/.test(para[0]))) flush(); para.push(line);
  }
  flush(); if (code !== null) output.push(`<pre><code>${esc(code.join('\n'))}</code></pre>`);
  return output.join('');
}
function chatDirection(text) { return /[\u0600-\u06ff]/.test(text)?'rtl':'ltr'; }
function current() {return data.issues.find(i => i.id === active);}
function localFeedback(selector, message, error=false) { const el=$(selector);el.textContent=message;el.hidden=!message;el.classList.toggle('error',error);el.setAttribute('role',error?'alert':'status');if(message)el.scrollIntoView({block:'nearest'}); }
function mayLeave() {return !dirty || window.confirm('You have unsaved English edits. Discard those edits?');}
function drawNav() {
  const selected = data.issues.filter(i => reviewStatus(i) === 'selected').length;
  $('#total-selected').textContent = selected;
  $('#all-progress').textContent = `${selected} of ${data.issues.length} findings selected`;
  $('#projects').innerHTML = [{id:'',count:data.issues.length},...data.projects].map(p => `<button class="project ${project===p.id?'active':''}" data-project="${esc(p.id)}" ${project===p.id?'aria-current="page"':''}><span>${esc(names[p.id] || p.id || 'All projects')}</span><span>${p.count}</span></button>`).join('');
  $('#projects').querySelectorAll('button').forEach(b => b.onclick = () => {project = b.dataset.project; drawNav(); drawList();});
}
function drawList() {
  const query = $('#search').value.trim().toLowerCase(), severity = $('#severity').value, status = $('#status').value;
  const filtered = data.issues.filter(i => (!project || i.project === project) && (!severity || i.severity === severity) && (!status || (status==='processed' ? i.review.processed : status==='unprocessed' ? !i.review.processed : reviewStatus(i) === status)) && (!query || `${i.id} ${i.title} ${i.area} ${i.body}`.toLowerCase().includes(query)));
  $('#project-title').textContent = names[project] || project || 'All projects'; $('#list-count').textContent = `${filtered.length} findings`;
  $('#findings').innerHTML = filtered.length ? filtered.map(i => `<button class="finding ${active===i.id?'active':''}" data-id="${i.id}" ${active===i.id?'aria-current="true"':''}><span class="finding-top"><span class="badge ${i.severity.toLowerCase()}">${i.severity}</span><span class="finding-id">${i.id}</span><span class="review-indicator">${[reviewStatus(i)==='selected'?'✓ Selected':reviewStatus(i)==='draft'?'Draft':'', i.review.processed?'Processed':''].filter(Boolean).join(' · ')}</span></span><span class="finding-title">${esc(i.title)}</span><span class="finding-area">${esc(i.area)}</span></button>`).join('') : '<p class="empty">No findings match. Try another filter.</p>';
  $('#findings').querySelectorAll('button').forEach(b => b.onclick = () => {if (!mayLeave()) return; dirty = false; active = b.dataset.id; tab = 'finding'; history.replaceState(null,'',`#${active}`); drawList(); drawDetail();});
}
function setTab(value) {
  tab = value;
  document.querySelectorAll('[data-tab]').forEach(b => {b.setAttribute('aria-selected', b.dataset.tab===tab); b.tabIndex = b.dataset.tab===tab ? 0 : -1;});
  document.querySelectorAll('[data-panel]').forEach(p => p.hidden = p.dataset.panel!==tab);
}
function drawDetail() {
  const i = current(); if (!i) return;
  if(!dirty || editorIssue!==active){editorIssue=active;editorVersion=i.review.version;}
  const unsavedSeverity = dirty && $('#selection-severity') ? $('#selection-severity').value : null;
  const unsaved = dirty && $('#draft-text') ? $('#draft-text').value : null;
  $('#detail').replaceChildren($('#detail-template').content.cloneNode(true));
  $('.severity-badge').textContent = i.severity; $('.severity-badge').classList.add(i.severity.toLowerCase());
  $('#toggle-processed').textContent=i.review.processed?'✓ Processed':'Mark processed';
  $('#toggle-processed').setAttribute('aria-pressed',String(i.review.processed));
  $('#toggle-processed').onclick=async()=>{const button=$('#toggle-processed');button.disabled=true;try{const result=await api('/api/processed',{id:i.id,processed:!i.review.processed});i.review.processed=result.processed;button.textContent=result.processed?'✓ Processed':'Mark processed';button.setAttribute('aria-pressed',String(result.processed));drawList();drawNav();notice(`${i.id} marked ${result.processed?'processed':'not processed'}.`);}catch(e){notice(e.message,true);}finally{button.disabled=false;}};
  $('.issue-id').textContent = i.id; $('.area').textContent = i.area; $('.issue-title').textContent = i.title;
  $('.source-link').textContent = i.evidence_label; $('.source-link').onclick = async () => {try {await navigator.clipboard.writeText(`${i.evidence_path}:${i.evidence_line}`);notice('Source location copied.');}catch {notice(`Source: ${i.evidence_path}:${i.evidence_line}`);}};
  $('.report-name').textContent = i.report;
  $('.report-body').innerHTML = markdown(i.body);
  $('#finding-severity').value=i.review.selected_severity || i.severity;
  $('#finding-severity').onchange=()=>{$('#selection-severity').value=$('#finding-severity').value;$('#selection-severity').dispatchEvent(new Event('change'));};
  $('#add-finding').textContent=reviewStatus(i)==='selected'?'Update selected':'Add to selected';
  $('#add-finding').onclick=()=>saveReview(true,$('#draft-text').value.trim()?$('#draft-text').value:i.body,$('#finding-severity').value);
  $('#copy-finding').onclick=async()=>{try{await navigator.clipboard.writeText(`### ${i.id} — ${i.title}\n\n${i.body}`);localFeedback('#finding-feedback','Finding copied as Markdown.');}catch{localFeedback('#finding-feedback','Could not copy. Allow clipboard access and retry.',true);}};

  $('.chat-count').textContent = i.review.messages.length ? `(${i.review.messages.length})` : '';
  $('.draft-dot').textContent = reviewStatus(i)==='selected' ? '✓' : i.review.draft ? '•' : '';
  $('.messages').innerHTML = i.review.messages.length ? i.review.messages.map((m, index) => `<div class="message ${m.role}" dir="${chatDirection(m.content)}"><div class="message-header"><div class="message-label">${m.role==='user'?'You':'Codex'}</div>${m.role==='assistant'?`<button type="button" class="copy-response" data-copy-message="${index}" aria-label="Copy response ${index + 1} as Markdown">Copy Markdown</button>`:''}</div><div class="prose" dir="${chatDirection(m.content)}">${markdown(m.content)}</div></div>`).join('') : '<p class="help">No discussion yet. Start with a question above or write your own.</p>';
  document.querySelectorAll('[data-copy-message]').forEach(button => {
    button.onclick = async () => {
      try {
        await navigator.clipboard.writeText(i.review.messages[Number(button.dataset.copyMessage)].content);
        button.textContent = 'Copied';
        notice('Response copied as Markdown.');
        setTimeout(() => {button.textContent = 'Copy Markdown';}, 2000);
      } catch {
        notice('Could not copy the response. Allow clipboard access in your browser and try again.', true);
      }
    };
  });
  $('#selection-severity').value=unsavedSeverity || i.review.selected_severity || i.severity;
  $('#finding-severity').value=$('#selection-severity').value;
  $('#selection-severity').onchange=()=>{$('#finding-severity').value=$('#selection-severity').value;dirty=true;$('.draft-status').textContent='Unsaved severity change';$('#approve').disabled=false;$('#approve').textContent='Approve & add to selected';};
  $('#draft-text').value = unsaved !== null ? unsaved : i.review.draft;
  $('#draft-text').oninput = () => {localFeedback('#review-feedback','');dirty = true; $('.draft-status').textContent = 'Unsaved edits'; $('#approve').textContent = 'Approve & add to selected'; $('#approve').disabled = false;};
  $('.stale-warning').hidden = !i.review.stale;
  $('.draft-status').textContent = dirty ? 'Unsaved edits' : reviewStatus(i)==='selected' ? '✓ Approved and saved to selected file' : i.review.draft ? 'Draft saved · awaiting your approval' : 'No draft yet';
  $('#approve').textContent = reviewStatus(i)==='selected' && !dirty ? '✓ Selected' : 'Approve & add to selected';
  $('#approve').disabled = reviewStatus(i)==='selected' && !dirty; $('#remove').hidden = reviewStatus(i)!=='selected';
  document.querySelectorAll('[data-tab]').forEach(b => {
    b.onclick = () => setTab(b.dataset.tab);
    b.onkeydown = e => {if (!['ArrowLeft','ArrowRight','Home','End'].includes(e.key)) return; e.preventDefault(); const tabs = ['finding','discuss','draft'];const index = e.key==='Home'?0:e.key==='End'?2:(tabs.indexOf(tab)+(e.key==='ArrowRight'?1:2))%3;setTab(tabs[index]); $(`[data-tab="${tabs[index]}"]`).focus();};
  });
  document.querySelectorAll('.generate-draft').forEach(b => b.onclick = () => startJob('draft'));
  document.querySelectorAll('[data-question]').forEach(b => b.onclick = () => {$('#question').value = b.dataset.question; $('#question').focus();});
  $('#question').value=questionBuffers.get(i.id)||'';
  $('#question').oninput=()=>questionBuffers.set(i.id,$('#question').value);
  $('#ask-form').onsubmit = e => {e.preventDefault(); startJob('ask', $('#question').value);};
  $('#save-draft').onclick = () => saveReview(false);
  $('#approve').onclick = () => saveReview(true);
  $('#remove').onclick = () => saveReview(false);
  setTab(tab); updateBusy();
}
function updateBusy() {
  if (!current()) return;
  const isHere = pending && pending.id === active;
  $('.job-status').hidden = !isHere;
  if (isHere) $('.job-label').textContent = pending.kind==='draft' ? 'Codex is preparing the English draft. You can browse other findings.' : 'Codex is reading the finding and your question…';
  document.querySelectorAll('.generate-draft, #ask-button').forEach(b => b.disabled = !!pending || !data.codex);
}
async function saveReview(approved, initialDraft=null, initialSeverity=null) {
  if(initialDraft!==null)$('#draft-text').value=initialDraft;
  if(initialSeverity!==null)$('#selection-severity').value=initialSeverity;
  const feedback=tab==='finding'?'#finding-feedback':'#review-feedback';
  const i = current(); const buttons = [...document.querySelectorAll('#save-draft,#approve,#remove,#add-finding')]; buttons.forEach(b => b.disabled=true);
  const submittedDraft=$('#draft-text').value, submittedSeverity=$('#selection-severity').value;
  localFeedback(feedback,'Saving…');
  try {
    const review = await api('/api/review',{id:i.id,draft:submittedDraft,approved,version:editorVersion,severity:submittedSeverity});
    i.review = review;
    if(active===i.id){editorVersion=review.version;dirty=$('#draft-text').value!==submittedDraft || $('#selection-severity').value!==submittedSeverity;drawDetail();}
    drawNav();drawList();
    if(active===i.id)localFeedback(feedback,approved?'Approved and added to selected-issues.md.':'Draft saved; this issue is not selected.');
    notice(approved ? `${i.id} approved and saved to selected-issues.md.` : `${i.id} saved as a draft. It is not in the selected file.`);
  } catch(e) {if(active===i.id)localFeedback(feedback,e.message,true);notice(e.message,true); buttons.forEach(b => b.disabled=false);}
}
async function startJob(kind, question='') {
  if (kind==='draft' && !mayLeave()) return;
  if (kind==='draft') {dirty = false; setTab('draft');}
  const i = current();
  try {
    const result = await api('/api/ask',{id:i.id,kind,question,version:i.review.version});
    pending = {id:i.id,kind,job:result.job}; localStorage.setItem('issue-desk-job', JSON.stringify(pending));
    if (kind==='ask') {i.review.messages.push({role:'user',content:question}); if((questionBuffers.get(i.id)||'')===question){questionBuffers.delete(i.id);if(active===i.id)$('#question').value='';}}
    notice(''); drawDetail(); poll();
  } catch(e) {notice(e.message,true);}
}
async function refreshIssue(id) {
  const latest = await api('/api/issues');
  data = latest; drawNav(); drawList();
  if (active===id && !dirty) drawDetail(); else updateBusy();
}
async function poll() {
  if (!pending) return;
  try {
    const job = await api(`/api/jobs/${pending.job}`);
    if (job.status==='done' || job.status==='error') {
      const finished = pending; pending = null;localStorage.removeItem('issue-desk-job');
      await refreshIssue(finished.id);
      notice(job.status==='error' ? job.error : `${finished.id}: ${finished.kind==='draft'?'English draft ready for your review.':'Codex answered in the discussion tab.'}`,job.status==='error');
      return;
    }
    updateBusy(); setTimeout(poll,1800);
  } catch(e) {pending=null;localStorage.removeItem('issue-desk-job');updateBusy();notice(`${e.message} If the server restarted, retry your request.`,true);}
}
let selectionRevision=null, selectionDirty=false;
function selectedMode(preview) {
  $('#selected-editor').hidden=preview;$('#selected-preview').hidden=!preview;
  $('#selected-edit-tab').setAttribute('aria-pressed',String(!preview));
  $('#selected-preview-tab').setAttribute('aria-pressed',String(preview));
  if(preview)$('#selected-preview').innerHTML=markdown($('#selected-editor').value);
}
async function loadSelection() {
  const doc=await api('/api/selection');selectionRevision=doc.revision;
  $('#selected-editor').value=doc.content;selectionDirty=false;
  $('#selected-save-status').textContent='Saved file content';
  if(!$('#selected-preview').hidden)selectedMode(true);
}
$('#open-selected').onclick=async()=>{
  $('#selected-dialog').showModal();$('#save-selected').disabled=true;
  try{await loadSelection();localFeedback('#selected-feedback','');}
  catch(e){localFeedback('#selected-feedback',e.message,true);}
  finally{$('#save-selected').disabled=selectionRevision===null;}
};
function closeSelection() {
  if(selectionDirty&&!confirm('Discard unsaved selected-file edits?'))return;
  selectionDirty=false;$('#selected-dialog').close();
}
$('#close-selected').onclick=closeSelection;
$('#selected-dialog').addEventListener('cancel',e=>{e.preventDefault();closeSelection();});
$('#selected-editor').oninput=()=>{selectionDirty=true;$('#selected-save-status').textContent='Unsaved file edits';localFeedback('#selected-feedback','');};
$('#selected-edit-tab').onclick=()=>selectedMode(false);
$('#selected-preview-tab').onclick=()=>selectedMode(true);
$('#reload-selected').onclick=async()=>{
  if(selectionDirty&&!confirm('Discard edits and reload the saved selected file?'))return;
  try{await loadSelection();localFeedback('#selected-feedback','File reloaded.');}catch(e){localFeedback('#selected-feedback',e.message,true);}
};
$('#save-selected').onclick=async()=>{
  $('#save-selected').disabled=true;
  try{
    const submitted=$('#selected-editor').value;
    const doc=await api('/api/selection',{content:submitted,revision:selectionRevision});
    selectionRevision=doc.revision;selectionDirty=$('#selected-editor').value!==submitted;
    if(!selectionDirty)$('#selected-editor').value=doc.content;
    if(!$('#selected-preview').hidden)selectedMode(true);
    $('#selected-save-status').textContent=selectionDirty?'Unsaved edits kept in editor':'Saved to selected-issues.md';
    await refreshIssue(active);localFeedback('#selected-feedback','Selected file saved. Issue selections are in sync.');
  }catch(e){localFeedback('#selected-feedback',e.message,true);}
  finally{$('#save-selected').disabled=false;}
};
const theme = localStorage.getItem('issue-desk-theme') || 'system'; $('#theme').value=theme;
function applyTheme(value) {if(value==='system') delete document.documentElement.dataset.theme;else document.documentElement.dataset.theme=value;localStorage.setItem('issue-desk-theme',value);}
applyTheme(theme); $('#theme').onchange=e=>applyTheme(e.target.value);
['search','severity','status'].forEach(id => $(`#${id}`).addEventListener(id==='search'?'input':'change',drawList));
window.addEventListener('beforeunload',e=>{if(dirty || selectionDirty || [...questionBuffers.values()].some(value=>value.trim())){e.preventDefault();e.returnValue='';}});
(async () => {
  try {
    data=await api('/api/issues');active=data.issues.some(i=>i.id===location.hash.slice(1))?location.hash.slice(1):data.issues[0]?.id;
    $('#connection').textContent=data.codex?'Local workspace · Codex connected':'Local workspace · Codex unavailable';
    if(!data.codex)notice('Install the Codex CLI and sign in with `codex login` to use discussions and translations.',true);
    drawNav();drawList();drawDetail();
    try{pending=JSON.parse(localStorage.getItem('issue-desk-job'));}catch{pending=null;}
    if(pending){updateBusy();poll();}
  } catch(e){$('#detail').textContent='Unable to load reports. Check the local server and reload.';notice(e.message,true);}
})();
