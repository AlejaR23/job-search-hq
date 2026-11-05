/* PC career tasks. Server owns prompts and records. */
async function pcState(){
 const data=await pcFetch('/api/ai/state');gotPostings(data.postings||[]);
 const running=data.tasks.find(t=>['queued','running'].includes(t.status));
 $('#requests').textContent=running?running.message:'Your existing daily scan runs on the PC. On-demand searches are awaiting setup.';
 if(CUR){const fresh=POSTINGS.find(p=>p._id===CUR._id);if(fresh){CUR=fresh;renderResult(CUR)}}return data;
}
async function pcInit(){
 CAP.sample={};CAP.downloads={};
 CAP.db={doc:path=>({update:async patch=>{
  if(!path.startsWith('postings/')||Object.keys(patch).some(k=>k!=='jobId'))throw Error('This change requires a separate reviewer.');
  return pcFetch('/api/ai/link',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:path.slice(9),jobId:patch.jobId})});
 }})};
 PH={maxCount:5,maxInputBytes:8*1024*1024,mediaTypes:['image/jpeg','image/png']};
 $('#r-file').accept=PH.mediaTypes.join(',');$('#r-photos').hidden=false;renderThumbs();
 $('#r-go').disabled=false;$('#s-go').disabled=true;$('#s-go').title='On-demand search setup is pending';
 const [state,files]=await Promise.all([pcState(),pcFetch('/api/cvs')]);gotCvs(files.files);
 const active=state.tasks.find(t=>['queued','running'].includes(t.status));
 if(active)pcResume(active.id,active.kind).catch(e=>toast(e.message,null,true));
}
function pcPause(ms){return new Promise(resolve=>setTimeout(resolve,ms))}
async function pcResume(id,kind){
 if(!OP)startOp(kind,CUR?CUR._id:'',null);
 try{for(;;){const state=await pcState(),task=state.tasks.find(t=>t.id===id);
  if(!task)throw Error('This task is no longer listed. Reload the page.');
  if(task.status==='done'){const r=POSTINGS.find(r=>r._id===task.result);if(r){CUR=r;renderResult(r)}return r}
  if(['failed','interrupted'].includes(task.status))throw Error(task.message);
  setOp(task.message+' You can close the page and return later.',true);await pcPause(1500);
 }}catch(e){$('#r-err').textContent=e.message;$('#r-err').hidden=false;throw e}finally{endOp()}
}
async function pcSubmit(payload){
 const data=await pcFetch('/api/ai/submit',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...payload,requestId:crypto.randomUUID()})});
 return pcResume(data.id,payload.kind);
}
analyze=async function(){
 if(OP)return;await IMGQ;$('#r-err').hidden=true;
 const posting={company:$('#r-company').value.trim(),role:$('#r-role').value.trim(),link:$('#r-link').value.trim(),text:$('#r-text').value.trim(),jobId:REVIEW_JOB||''};
 startOp('analyze','',null);
 try{const images=[];for(const image of await prepImages()){images.push(await new Promise((resolve,reject)=>{const r=new FileReader;r.onload=()=>resolve(String(r.result).split(',')[1]);r.onerror=reject;r.readAsDataURL(image)}))}
 const result=await pcSubmit({kind:'analyze',posting,images});if(result){$('#f-review').reset();clearImages();REVIEW_JOB='';store.set('rdraft',null);$('#r-msg').textContent='Analysis saved. Choose a document below if you want one.';$('#result').scrollIntoView({block:'start'})}
 }catch(e){$('#r-err').textContent=e.message;$('#r-err').hidden=false}finally{if(OP)endOp()}
};
makeDoc=async function(kind,sentiment=''){
 if(OP||!CUR)return;startOp(kind,CUR._id,null);
 try{await pcSubmit({kind,postingId:CUR._id,sentiment,withoutSentiment:kind==='letter'&&!sentiment.trim()});if(kind==='letter')SENT.id='';renderResult(CUR)}
 catch(e){toast(e.message,null,true)}finally{if(OP)endOp()}
};
downloadCv=async function(id){location.assign('/api/cvs/'+encodeURIComponent(id))};
docBlock=function(title,which,text,extra=''){return `<section class="sec" data-sec="${which}"><div class="doc-h"><h3>${title}</h3><button class="btn ghost" type="button" data-doc="${which}" data-do="copy">Copy</button><button class="btn ghost" type="button" data-pc-doc="${which}">Download draft .docx</button></div><pre class="doc">${esc(text)}</pre>${extra}</section>`};
document.addEventListener('click',async e=>{const b=e.target.closest('[data-pc-doc]');if(!b||!CUR)return;e.stopImmediatePropagation();b.disabled=true;
 try{const r=await fetch('/api/ai/export',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:CUR._id,kind:b.dataset.pcDoc==='cv'?'cv':'letter'})});
 if(!r.ok)throw Error('Could not export this draft. Sign in again if your session ended.');
 const blob=await r.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=(/filename="([^"]+)"/.exec(r.headers.get('Content-Disposition')||'')||[])[1]||'HQ_DRAFT.docx';a.click();setTimeout(()=>URL.revokeObjectURL(url),30000);
 }catch(x){toast(x.message,null,true)}finally{b.disabled=false}},true);
$('#f-search').addEventListener('submit',e=>{e.preventDefault();e.stopImmediatePropagation();toast('On-demand searches are awaiting setup. Your daily scan stays in place.',null,true)},true);
