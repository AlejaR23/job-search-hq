/* PC backend. Workbook remains the source of truth. */
let busy=false,READY=false,seenView=null;
const CAP={db:null,sample:null,downloads:null},NOTED=new Set(),TOOL_VIEWS=['search','review'];
const nowISO=()=>new Date().toISOString();
const use=()=>Promise.resolve(null);
function pcDate(value){const s=String(value||'');if(!/^\d{16,20}$/.test(s))return s;const d=new Date(Number(s)/1e6);return Number.isNaN(d.getTime())?'Date unavailable':d.toLocaleDateString(undefined,{year:'numeric',month:'short',day:'numeric'})}
let PC_WAITING=false,PC_LAST_WRITE='';
async function pcHealth(){try{const h=await pcFetch('/api/health');let el=document.getElementById('pc-health');if(!el){el=document.createElement('small');el.id='pc-health';el.style.display='block';$('#sync').after(el)}el.textContent=h.scan?.message||'Scan status unavailable.'}catch{}}
async function pcWrites(){
 try{const data=await pcFetch('/api/writes'),items=data.writes||[];
 const active=items.find(w=>['waiting','applying','conflict','needs_check'].includes(w.status));
 PC_WAITING=!!active;
 let box=document.getElementById('pc-saves');
 if(!box){box=document.createElement('aside');box.id='pc-saves';box.className='banner';box.setAttribute('aria-live','polite');document.querySelector('.top').after(box)}
 const w=active||items[0];box.hidden=!w;if(!w)return;
 box.replaceChildren();const text=document.createElement('span');text.textContent=w.label+': '+w.message;box.append(text);
 if(['waiting','conflict','needs_check','failed'].includes(w.status)){
 const b=document.createElement('button');b.className='btn ghost';b.textContent=w.status==='waiting'?'Cancel waiting edit':'I checked the spreadsheet; dismiss';
 b.onclick=async()=>{try{await pcFetch('/api/writes/dismiss',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:w.id})});await pcWrites();await reloadJobs(true)}catch(e){toast(e.message,null,true)}};box.append(b)}
 const stamp=w.id+':'+w.status;
 if(PC_LAST_WRITE&&PC_LAST_WRITE!==stamp&&w.status==='saved')await reloadJobs(true);
 PC_LAST_WRITE=stamp;
 }catch{ /* Preserve the last known pending state during a dropped connection. */ }
}
function checkText(j){return String(j._check||'')}
async function pcFetch(path,options={}){
 const r=await fetch(path,{cache:'no-store',...options});
 if(r.status===401){location.assign('/login');throw Error('Please sign in again.')}
 const d=await r.json();if(!r.ok)throw Error(d.error||'Could not complete this change.');return d;
}
async function reloadJobs(silent=false){
 try{const d=await pcFetch('/api/data');Object.assign(D,d);
 D.jobs.forEach(j=>{enrich(j);if(NOTED.has(j._id))j._noteSaved=true});
 linkSiblings();READY=true;fillAdd();render();syncLabel();
 if(!silent)toast('Reloaded from your spreadsheet');
 }catch(e){$('#sync').textContent='Connection lost. Your unsaved edits are still here.';if(!silent)toast(e.message,null,true)}
}
function syncLabel(){ $('#sync').textContent=`${D.jobs.length} jobs · spreadsheet connected`; }
async function boot(){
 $('#requests').textContent='Search automation is awaiting setup. Your existing daily scan stays in place.';
 await reloadJobs(true);
 await pcWrites();
 await pcHealth();
 await pcInit();
 const b=document.createElement('button');b.className='btn ghost';b.textContent='Sign out';
 b.onclick=async()=>{await pcFetch('/api/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});location.assign('/login')};
 $('#sync').parentNode.append(b);
 setInterval(async()=>{if(busy||document.hidden)return;await pcWrites();await pcHealth();try{const d=await pcFetch('/api/version');if(d.version!==D.version)await reloadJobs(true)}catch{}},5000);
}
async function post(url,p){
 try{
 if(PC_WAITING){toast('An edit is waiting. Check the save message at the top first.',null,true);return null}
 const j=p.id?(p.sheet==='Contacts'?D.contacts:D.jobs).find(j=>j._id===p.id):null;
 const payload={...p,version:D.version,requestId:crypto.randomUUID()};
 if(j){payload.row=j._row;payload.expect=p.sheet==='Contacts'?{Person:j.Person}:{Company:j.Company,Role:j.Role}}
 const d=await pcFetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
 if(d.queued){await pcWrites();toast('Your edit is waiting for Excel. It is not saved to the spreadsheet yet.',null,true);return null}
 D.version=d.version;
 await pcWrites();
 if(url==='/api/add')await reloadJobs(true);
 return d;
 }catch(e){await pcWrites();toast(e.message,null,true);return null}
}
function openSoon(id){if(byKey(id))openJob(id)}
