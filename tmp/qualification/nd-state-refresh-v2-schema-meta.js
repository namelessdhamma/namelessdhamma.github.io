(async()=>{
const crypto=require('crypto');

const OWNER='namelessdhamma';
const REPO='nameless-dhamma-vault';
const STATE_HEAD_ID='1gB6zqJPsQQmv7cT3nxFOtM_EcrUqC3v_MN9ChymclOQ';
const VISUAL_REGISTRY_ID='13TgCxf91Rb0fJd3APqb_b83U-xvCKuCJeI98LCxXPg4';
const LITERATURE_TOM2_ID='1ZN7xXmoNFmJLdtYtJLh4MYPzpr0h1PCA';

const PAT=process.env.ND_GITHUB_PAT||'';
const GMAIL=process.env.ND_GOOGLE_CLIENT_EMAIL||'';
const GKEY=process.env.ND_GOOGLE_PRIVATE_KEY_B64||'';
const OKEY=process.env.OPENAI_API_KEY||'';
const OMODEL=process.env.OPENAI_MODEL||'';
const GKEY2=process.env.GROQ_API_KEY||'';
const GMODEL=process.env.GROQ_MODEL||'';

if(!PAT||!GMAIL||!GKEY) throw new Error('RUNTIME_SECRETS_MISSING');

function sha(x){return crypto.createHash('sha256').update(x).digest('hex');}
function b64u(x){return Buffer.from(x).toString('base64').replace(/=/g,'').replace(/\+/g,'-').replace(/\//g,'_');}
function noCyr(x){return !/[\u0400-\u04FF]/.test(String(x||''));}
function hasThai(x){return /[\u0E00-\u0E7F]/.test(String(x||''));}
function wait(ms){return new Promise(r=>setTimeout(r,ms));}
function parseModelJson(text){
 const raw=String(text||'').trim();
 if(!raw)throw new Error('MODEL_JSON_EMPTY');
 try{return JSON.parse(raw);}catch(first){}
 const fenced=raw.match(/^\`\`\`(?:json)?\s*([\s\S]*?)\s*\`\`\`$/i);
 if(fenced){
  try{return JSON.parse(fenced[1].trim());}catch(e){throw new Error('MODEL_JSON_FENCE_INVALID:'+String(e.message||e));}
 }
 const a=raw.indexOf('{'),b=raw.lastIndexOf('}');
 if(a>=0&&b>a){
  try{return JSON.parse(raw.slice(a,b+1));}catch(e){throw new Error('MODEL_JSON_OBJECT_INVALID:'+String(e.message||e));}
 }
 throw new Error('MODEL_JSON_INVALID');
}

async function gh(path,opts){
 const o=Object.assign({method:'GET',headers:{}},opts||{});
 o.headers=Object.assign({Authorization:'Bearer '+PAT,Accept:'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'ND-state-refresh-v2'},o.headers||{});
 const r=await fetch('https://api.github.com/repos/'+OWNER+'/'+REPO+path,o);
 const t=await r.text();
 if(!r.ok) throw new Error('GITHUB_'+r.status+':'+path+':'+t.slice(0,300));
 return t?JSON.parse(t):{};
}
async function file(path){
 const p=path.split('/').map(encodeURIComponent).join('/');
 try{
  const j=await gh('/contents/'+p);
  return {sha:j.sha,text:Buffer.from(String(j.content||'').replace(/\n/g,''),'base64').toString('utf8')};
 }catch(e){if(String(e).includes('GITHUB_404'))return null;throw e;}
}
async function commit(files,msg){
 const ref=await gh('/git/ref/heads/main');
 const parent=ref.object.sha;
 const pc=await gh('/git/commits/'+parent);
 const tree=[];
 for(const p of Object.keys(files)){
  const b=await gh('/git/blobs',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({content:files[p],encoding:'utf-8'})});
  tree.push({path:p,mode:'100644',type:'blob',sha:b.sha});
 }
 const nt=await gh('/git/trees',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({base_tree:pc.tree.sha,tree:tree})});
 const nc=await gh('/git/commits',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({message:msg,tree:nt.sha,parents:[parent]})});
 await gh('/git/refs/heads/main',{method:'PATCH',headers:{'content-type':'application/json'},body:JSON.stringify({sha:nc.sha,force:false})});
 return nc.sha;
}

async function gtoken(){
 const now=Math.floor(Date.now()/1000);
 const pem=Buffer.from(GKEY,'base64').toString('utf8');
 const h=b64u(JSON.stringify({alg:'RS256',typ:'JWT'}));
 const p=b64u(JSON.stringify({iss:GMAIL,scope:'https://www.googleapis.com/auth/drive.readonly',aud:'https://oauth2.googleapis.com/token',iat:now,exp:now+3600}));
 const u=h+'.'+p;
 const sig=crypto.sign('RSA-SHA256',Buffer.from(u),pem);
 const form=new URLSearchParams({grant_type:'urn:ietf:params:oauth:grant-type:jwt-bearer',assertion:u+'.'+b64u(sig)});
 const r=await fetch('https://oauth2.googleapis.com/token',{method:'POST',headers:{'content-type':'application/x-www-form-urlencoded'},body:form});
 const t=await r.text(); if(!r.ok)throw new Error('GOOGLE_TOKEN_'+r.status);
 return JSON.parse(t).access_token;
}
async function dread(tok,id,native){
 const url=native?'https://www.googleapis.com/drive/v3/files/'+encodeURIComponent(id)+'/export?mimeType=text%2Fplain':'https://www.googleapis.com/drive/v3/files/'+encodeURIComponent(id)+'?alt=media';
 const r=await fetch(url,{headers:{Authorization:'Bearer '+tok}});
 const b=Buffer.from(await r.arrayBuffer());
 if(!r.ok)throw new Error('DRIVE_READ_'+r.status+':'+id);
 return b;
}
async function rev(tok,id){
 const r=await fetch('https://www.googleapis.com/drive/v3/files/'+encodeURIComponent(id)+'/revisions?pageSize=100&fields=revisions(id%2CmodifiedTime%2Csize)',{headers:{Authorization:'Bearer '+tok}});
 if(!r.ok)return null;
 const a=(await r.json()).revisions||[];return a.length?a[a.length-1]:null;
}

function compact(h){
 if(!h||typeof h!=='object')return null;
 return {
  workstream_id:h.workstream_id||null,
  domain:h.domain||null,
  status_class:h.status_class||null,
  updated_at:h.updated_at||null,
  material_delta:h.material_delta||null,
  open_gaps:Array.isArray(h.open_gaps)?h.open_gaps.slice(0,8):[],
  next_meaningful_step:h.next_meaningful_step||null,
  authority_ceiling:h.authority_ceiling||null,
  source_signatures:h.source_signatures||{}
 };
}
function note(t1,t2,a,b,type){
 return ['---','type: '+(type||'nd-human-projection'),'language_order: th-en','title_th: '+JSON.stringify(t1),'title_en: '+JSON.stringify(t2),'authority: derived-readout','refreshed_at: '+new Date().toISOString().slice(0,10),'---','','# '+t1+' — '+t2,'','## ภาษาไทย','',String(a||'').trim(),'','## English','',String(b||'').trim(),''].join('\n');
}

async function ai(system,user,emergencyUser){
 async function call(url,key,model,userText){
  const body={model:model,messages:[{role:'system',content:system},{role:'user',content:userText}],response_format:{type:'json_object'},max_tokens:2200};
  const payload=JSON.stringify(body);
  console.log('MODEL_REQUEST_META '+JSON.stringify({model:model,input_bytes:Buffer.byteLength(payload)}));
  let r=await fetch(url,{method:'POST',headers:{Authorization:'Bearer '+key,'content-type':'application/json'},body:payload});
  let t=await r.text();
  const hardQuota=(r.status===429 && /insufficient_quota|no credits remaining/i.test(t));
  if(r.status===429 && !hardQuota){
    await wait(18000);
    r=await fetch(url,{method:'POST',headers:{Authorization:'Bearer '+key,'content-type':'application/json'},body:payload});
    t=await r.text();
  }
  if(!r.ok)throw new Error('MODEL_'+r.status+':'+t.slice(0,250));
  const j=JSON.parse(t);return j.choices&&j.choices[0]&&j.choices[0].message?j.choices[0].message.content:'';
 }
 if(OKEY&&OMODEL){
  try{return {provider:'openai',model:OMODEL,text:await call('https://api.openai.com/v1/chat/completions',OKEY,OMODEL,user)};}catch(e){console.error('OPENAI_PRIMARY_FAILED',String(e).slice(0,350));}
 }
 if(GKEY2&&GMODEL){
  try{return {provider:'groq',model:GMODEL,text:await call('https://api.groq.com/openai/v1/chat/completions',GKEY2,GMODEL,user)};}
  catch(e){
   if(emergencyUser && /MODEL_413:/.test(String(e))){
    console.error('GROQ_413_RETRY_COMPACT',String(e).slice(0,260));
    return {provider:'groq',model:GMODEL,text:await call('https://api.groq.com/openai/v1/chat/completions',GKEY2,GMODEL,emergencyUser)};
   }
   throw e;
  }
 }
 throw new Error('NO_MODEL_PROVIDER');
}

function fallback(ctx){
 const H=ctx.h;
 const r=H.research||{}, l=H.literature||{}, v=H.visual||{}, a=H.automation_agent||{}, ar=H.architecture_control||{}, t=H.tooling||{}, w=H.true_writing||{};
 const tasks=[
  {owner:'True Research',status:r.status_class||'ACTIVE',title_th:'ดำเนินการวิจัยแนวหน้าปัจจุบัน',title_en:'Continue the current research frontier',summary_th:'ตรวจหลักฐานตาม frontier ปัจจุบันและรักษาระดับความมั่นใจของข้อสรุป',summary_en:'Inspect evidence for the current frontier while preserving the evidential strength of conclusions.'},
  {owner:'True Memory',status:'ACTIVE',title_th:'ดูแลสถานะมนุษย์ใน Obsidian',title_en:'Maintain the human state in Obsidian',summary_th:'ทำให้ Obsidian แสดงสถานะล่าสุดเป็นภาษาไทยก่อนและภาษาอังกฤษตามหลัง',summary_en:'Keep Obsidian aligned with the latest state, Thai first and English second.'},
  {owner:'True Developer',status:a.status_class||'ACTIVE',title_th:'พัฒนาระบบอัตโนมัติ ND',title_en:'Develop ND automation',summary_th:'ทำให้ runtime ภายนอกทำงานต่อเนื่องและลดการพึ่งพาการทำงานด้วยมือ',summary_en:'Keep the external runtime operational and reduce manual intervention.'},
  {owner:'True Writer',status:w.status_class||'DEVELOPMENT',title_th:'พัฒนา True Writer',title_en:'Develop True Writer',summary_th:'ดำเนินการตาม handoff ล่าสุดโดยไม่ยกระดับ development เป็น production โดยปริยาย',summary_en:'Continue from the latest handoff without implicitly promoting development into production.'},
  {owner:'True Version',status:ar.status_class||'ACTIVE',title_th:'ตรวจการเปลี่ยนแปลงสถาปัตยกรรม',title_en:'Inspect architecture changes',summary_th:'ตรวจ material delta และการเข้ากันได้ก่อนการยอมรับเข้าสู่ production',summary_en:'Inspect material deltas and compatibility before production adoption.'}
 ];
 return {
  domains:{
   architecture:{status:'CURRENT_AUTHORITY_VERIFIED',summary:ar.material_delta||'Authority verified from StateHead and bound Registry.',open_gaps:ar.open_gaps||[],next_step:ar.next_meaningful_step||null,evidence_level:'AUTHORITY_PLUS_HANDOFF'},
   research:{status:r.status_class||'UNKNOWN',summary:r.material_delta||'Research handoff available.',open_gaps:r.open_gaps||[],next_step:r.next_meaningful_step||null,evidence_level:'DURABLE_HANDOFF'},
   literature:{status:l.status_class||'UNKNOWN',summary:l.material_delta||'Literature handoff available.',open_gaps:l.open_gaps||[],next_step:l.next_meaningful_step||null,evidence_level:'HANDOFF_PLUS_REVISION_SIGNAL'},
   visual:{status:v.status_class||'UNKNOWN',summary:v.material_delta||'Visual handoff available.',open_gaps:v.open_gaps||[],next_step:v.next_meaningful_step||null,evidence_level:'HANDOFF_PLUS_REVISION_SIGNAL'},
   development:{status:a.status_class||'UNKNOWN',summary:a.material_delta||'Automation development handoff available.',open_gaps:a.open_gaps||[],next_step:a.next_meaningful_step||null,evidence_level:'DURABLE_HANDOFF'},
   tooling:{status:t.status_class||'UNKNOWN',summary:t.material_delta||'Tooling handoff available.',open_gaps:t.open_gaps||[],next_step:t.next_meaningful_step||null,evidence_level:'DURABLE_HANDOFF'}
  },
  coverage:{architecture:'FULL_AUTHORITY',research:r?'HANDOFF':'GAP',literature:l?'HANDOFF':'GAP',visual:v?'HANDOFF':'GAP',development:a?'HANDOFF':'GAP',tooling:t?'HANDOFF':'GAP',whole_nd_claim:'BOUNDED_NON_AUTHORITATIVE_SNAPSHOT'},
  inspection_queue:[],
  tasks:tasks,
  human:{
   now_th:'ระบบได้ตรวจ StateHead และ Registry ล่าสุดแล้ว และสร้าง snapshot ใหม่ของ ND สำหรับการอ่านใน Obsidian โดยไม่เปลี่ยน authority หลัก',
   now_en:'The system verified the latest StateHead and Registry and created a new ND snapshot for Obsidian without changing canonical authority.',
   changes_th:'รอบนี้บันทึกสถานะใหม่จาก authority, durable handoffs และสัญญาณล่าสุดที่ตรวจได้',
   changes_en:'This run records a fresh state from authority, durable handoffs, and the latest observable signals.',
   architecture_th:'StateHead และ Registry ที่ผูกไว้ผ่านการตรวจสอบ hash แล้ว การเปลี่ยน production ยังต้องผ่าน True Version',
   architecture_en:'The StateHead and bound Registry passed hash verification. Production changes still require True Version governance.',
   research_th:'สถานะการวิจัยมาจาก durable research handoff เท่านั้น ส่วนช่องว่างที่ยังไม่ยืนยันยังคงเป็นช่องว่าง',
   research_en:'Research state comes only from the durable research handoff; unverified gaps remain gaps.',
   literature_th:'สถานะวรรณกรรมใช้ durable handoff และ revision signal โดยไม่เดาความตั้งใจจาก metadata เพียงอย่างเดียว',
   literature_en:'Literature state uses the durable handoff and revision signals without inferring intent from metadata alone.',
   visual_th:'สถานะภาพใช้ Visual handoff และ registry signal โดยไม่ยกระดับงานพัฒนาเป็น canonical โดยปริยาย',
   visual_en:'Visual state uses the visual handoff and registry signal without implicitly promoting development into canonical status.',
   automation_th:'runtime ภายนอกทำหน้าที่ตรวจและเขียน snapshot ใหม่ทุกครั้งที่รัน ส่วน AI เป็นตัวช่วยสังเคราะห์ ไม่ใช่ authority',
   automation_en:'The external runtime verifies and rewrites the snapshot on every run. AI assists synthesis but is not an authority.',
   obsidian_th:'Obsidian เป็นอินเทอร์เฟซมนุษย์หลัก ใช้ภาษาไทยก่อนและภาษาอังกฤษตามหลัง และยังคงเป็น projection ที่ไม่ใช่ source of truth',
   obsidian_en:'Obsidian is the primary human interface, Thai first and English second, while remaining a non-authoritative projection.'
  }
 };
}

const started=new Date().toISOString();
const tok=await gtoken();
const head=JSON.parse((await dread(tok,STATE_HEAD_ID,true)).toString('utf8').trim());
const regId=head.capability_registry&&head.capability_registry.canonical_artifact_id;
const regHash=head.capability_registry&&head.capability_registry.registry_hash;
if(!regId||!regHash)throw new Error('STATEHEAD_BINDING_INCOMPLETE');
const rb=await dread(tok,regId,false);
const actual=sha(rb);
if(actual!==regHash)throw new Error('REGISTRY_HASH_MISMATCH');
const registry=JSON.parse(rb.toString('utf8'));
const litRev=await rev(tok,LITERATURE_TOM2_ID);
const visRev=await rev(tok,VISUAL_REGISTRY_ID);

const hp={
 architecture_control:'.github/nd-whole-state/handoffs/architecture-control.json',
 automation_agent:'.github/nd-whole-state/handoffs/automation-agent.json',
 true_writing:'.github/nd-whole-state/handoffs/true-writing.json',
 research:'.github/nd-whole-state/handoffs/research.json',
 literature:'.github/nd-whole-state/handoffs/literature.json',
 visual:'.github/nd-whole-state/handoffs/visual.json',
 tooling:'.github/nd-whole-state/handoffs/tooling.json'
};
const H={}, shas={};
for(const k of Object.keys(hp)){const f=await file(hp[k]);if(f){shas[k]=f.sha;try{H[k]=compact(JSON.parse(f.text));}catch(e){H[k]=null;}}}
const prevF=await file('.github/nd-whole-state/state.json');
let prev={};if(prevF){try{prev=JSON.parse(prevF.text);}catch(e){}}
const cr=await gh('/commits?per_page=25');
const commits=(cr||[]).map(c=>({sha:c.sha,message:c.commit?String(c.commit.message||'').split('\n')[0]:'',at:c.commit&&c.commit.committer?c.commit.committer.date:null})).filter(x=>x.message&&!x.message.startsWith('state-refresh:')&&!x.message.startsWith('Vault sync from Android')).slice(0,15);

const authority={
 state_head:{file_id:STATE_HEAD_ID,head_id:head.head_id,head_hash:head.head_hash,record_hash:head.record_hash,published_at:head.published_at},
 registry:{id:head.capability_registry.registry_id,version:head.capability_registry.registry_version,artifact_id:regId,sha256:actual,component_count:Array.isArray(registry.components)?registry.components.length:null},
 latest_bundle:head.durable_record_store&&head.durable_record_store.latest_bundle?head.durable_record_store.latest_bundle:null,
 topology:{durable_authority:'StateHead -> exact Registry -> governed Google Drive',github_obsidian:'NON_AUTHORITATIVE_PROJECTION'}
};
const sourceSig=sha(Buffer.from(JSON.stringify({head:authority.state_head.head_hash,reg:actual,bundle:authority.latest_bundle,handoffs:shas,lit:litRev?litRev.id:null,vis:visRev?visRev.id:null,commits:commits.map(x=>x.sha)})));

let semantic=null, model={provider:'none',model:'none'}, semanticRefresh='REUSED';
if(prev&&prev.source_signature===sourceSig&&prev.semantic){
 semantic=prev.semantic;model=prev.model||model;
}else{
 const modelHandoffs=Object.fromEntries(Object.entries(H).map(([k,v])=>[k,v?{
  workstream_id:v.workstream_id||null,
  domain:v.domain||null,
  status_class:v.status_class||null,
  updated_at:v.updated_at||null,
  material_delta:String(v.material_delta||'').slice(0,900),
  open_gaps:Array.isArray(v.open_gaps)?v.open_gaps.slice(0,5).map(x=>String(x).slice(0,360)):[],
  next_meaningful_step:String(v.next_meaningful_step||'').slice(0,700),
  authority_ceiling:v.authority_ceiling||null
 }:null]));
 const compactEvidence={
  authority:{
   state_head:{head_id:authority.state_head.head_id,published_at:authority.state_head.published_at},
   registry:{id:authority.registry.id,version:authority.registry.version,component_count:authority.registry.component_count},
   topology:authority.topology
  },
  handoffs:modelHandoffs,
  revision_signals:{
   literature:litRev?{id:litRev.id,modifiedTime:litRev.modifiedTime||null}:null,
   visual:visRev?{id:visRev.id,modifiedTime:visRev.modifiedTime||null}:null
  },
  recent_git_signals:commits.slice(0,8).map(x=>({sha:x.sha,message:String(x.message||'').slice(0,180),at:x.at}))
 };
 const emergencyEvidence={
  a:{head:authority.state_head.head_id,registry:authority.registry.version,components:authority.registry.component_count},
  d:Object.fromEntries(Object.entries(modelHandoffs).map(([k,v])=>[k,v?{
   s:v.status_class,
   delta:String(v.material_delta||'').slice(0,160),
   next:String(v.next_meaningful_step||'').slice(0,180),
   gap:Array.isArray(v.open_gaps)&&v.open_gaps.length?String(v.open_gaps[0]).slice(0,120):null
  }:null])),
  sig:{lit:litRev?litRev.id:null,vis:visRev?visRev.id:null}
 };
 const sys=[
  'You are the ND State Pre-Agent. Synthesize a conservative current-state snapshot from bounded evidence.',
  'Authority precedence: fresh StateHead and exact bound Registry, then durable handoffs, then raw revision signals, then Git commits as non-authoritative signals only.',
  'Never promote development or qualification to production. Never invent missing chat conclusions. Mark gaps.',
  'For Dhamma research never infer causal ConditionEdges from textual order.',
  'Return JSON only with keys domains, coverage, inspection_queue, tasks, human.',
  'domains must contain architecture,research,literature,visual,development,tooling; each has status,summary,open_gaps,next_step,evidence_level.',
  'tasks items: owner,status,title_th,title_en,summary_th,summary_en. Allowed owner: True Research, True Memory, True Developer, True Writer, True Visual, True SMM, True Version, ND Agent.',
  'human keys: now_th,now_en,changes_th,changes_en,architecture_th,architecture_en,research_th,research_en,literature_th,literature_en,visual_th,visual_en,automation_th,automation_en,obsidian_th,obsidian_en.',
  'Human fields and task titles/summaries must contain no Cyrillic. Thai first, English duplicate. Be concise.'
 ].join('\n');
 try{
  const mr=await ai(sys,JSON.stringify(compactEvidence),JSON.stringify(emergencyEvidence));
  const x=parseModelJson(mr.text);
  if(!x.domains||!x.coverage||!Array.isArray(x.inspection_queue)||!Array.isArray(x.tasks)||!x.human){
   console.error('MODEL_SCHEMA_META '+JSON.stringify({
    top_keys:(x&&typeof x==='object'&&!Array.isArray(x)?Object.keys(x).slice(0,24):[]),
    value_type:Array.isArray(x)?'array':typeof x,
    domains_type:x&&typeof x==='object'?(Array.isArray(x.domains)?'array':typeof x.domains):'missing',
    coverage_type:x&&typeof x==='object'?(Array.isArray(x.coverage)?'array':typeof x.coverage):'missing',
    inspection_queue_type:x&&typeof x==='object'?(Array.isArray(x.inspection_queue)?'array':typeof x.inspection_queue):'missing',
    tasks_type:x&&typeof x==='object'?(Array.isArray(x.tasks)?'array':typeof x.tasks):'missing',
    human_type:x&&typeof x==='object'?(Array.isArray(x.human)?'array':typeof x.human):'missing'
   }));
   throw new Error('MODEL_SCHEMA');
  }
  if(!noCyr(JSON.stringify(x.tasks))||!noCyr(JSON.stringify(x.human)))throw new Error('MODEL_CYRILLIC');
  for(const k of Object.keys(x.human).filter(k=>k.endsWith('_th')))if(!hasThai(x.human[k]))throw new Error('MODEL_THAI_'+k);
  semantic=x;model={provider:mr.provider,model:mr.model};semanticRefresh='MODEL_REFRESHED';
 }catch(e){
  console.error('MODEL_SYNTHESIS_FALLBACK',String(e).slice(0,500));
  semantic=fallback({h:H});model={provider:'deterministic-fallback',model:'none'};semanticRefresh='FALLBACK_REFRESHED';
 }
}

const ver=Number(prev&&prev.state_version?prev.state_version:0)+1;
const run='ND-STATE-REFRESH-'+Date.now();
const state={
 contract_id:'ND-WHOLE-STATE-CONTROL-V2',
 state_version:ver,
 run_id:run,
 authoritative:false,
 overwrite_policy:'ALWAYS_ON_SUCCESSFUL_RUN',
 status:'OBSERVED',
 observed_at:started,
 source_signature:sourceSig,
 semantic_refresh:semanticRefresh,
 model:model,
 authority_snapshot:authority,
 source_manifest:{handoff_shas:shas,literature_tom2_revision_id:litRev?litRev.id:null,visual_registry_revision_id:visRev?visRev.id:null,recent_git_signal_shas:commits.map(x=>x.sha)},
 semantic:semantic,
 governance_note:'Non-authoritative whole-state snapshot. Fresh authority must be resolved again before canonical mutation.'
};

const h=semantic.human;
const files={
 '.github/nd-whole-state/state.json':JSON.stringify(state,null,2)+'\n',
 '.github/nd-state-refresh-v2/last-run.json':JSON.stringify({run_id:run,state_version:ver,observed_at:started,status:'PASS',semantic_refresh:semanticRefresh,model:model,authority_verified:true},null,2)+'\n',
 '00 ตอนนี้ — Now.md':note('ตอนนี้','Now',h.now_th,h.now_en),
 '03 การเปลี่ยนแปลง — Changes.md':note('การเปลี่ยนแปลง','Changes',h.changes_th,h.changes_en),
 'ND/สถาปัตยกรรมและการกำกับดูแล — Architecture and Governance.md':note('สถาปัตยกรรมและการกำกับดูแล','Architecture and Governance',h.architecture_th,h.architecture_en),
 'ND/การวิจัยนิพพาน — Nibbana Research.md':note('การวิจัยนิพพาน','Nibbāna Research',h.research_th,h.research_en),
 'ND/หนังสือและงานเขียน — Books and Writing.md':note('หนังสือและงานเขียน','Books and Writing',h.literature_th,h.literature_en),
 'ND/ระบบภาพ — Visual System.md':note('ระบบภาพ','Visual System',h.visual_th,h.visual_en),
 'ND/ระบบอัตโนมัติและเครื่องมือ — Automation and Tools.md':note('ระบบอัตโนมัติและเครื่องมือ','Automation and Tools',h.automation_th,h.automation_en),
 'ND/อินเทอร์เฟซ Obsidian — Obsidian Interface.md':note('อินเทอร์เฟซ Obsidian','Obsidian Interface',h.obsidian_th,h.obsidian_en)
};

const owners={
 'True Research':['เจ้าของ True Research','Owner True Research'],
 'True Memory':['เจ้าของ True Memory','Owner True Memory'],
 'True Developer':['เจ้าของ True Developer','Owner True Developer'],
 'True Writer':['เจ้าของ True Writer','Owner True Writer'],
 'True Visual':['เจ้าของ True Visual','Owner True Visual'],
 'True SMM':['เจ้าของ True SMM','Owner True SMM'],
 'True Version':['เจ้าของ True Version','Owner True Version'],
 'ND Agent':['เจ้าของ ND Agent','Owner ND Agent']
};
const cdir='ND Interface/07 Human/Graph/4 Current/';
for(const o of Object.keys(owners)){
 const p=owners[o],ts=semantic.tasks.filter(t=>t.owner===o);
 const th=ts.length?ts.map(t=>'- **'+t.title_th+'** · '+t.status+'\n  '+t.summary_th).join('\n'):'ยังไม่มีงาน active ที่รองรับด้วยหลักฐานใน snapshot ปัจจุบัน';
 const en=ts.length?ts.map(t=>'- **'+t.title_en+'** · '+t.status+'\n  '+t.summary_en).join('\n'):'No evidence-supported active task is present in the current snapshot.';
 files[cdir+p[0]+' — '+p[1]+'.md']=note(p[0],p[1],th,en,'nd-graph-node');
}
const order=Object.keys(owners);
files[cdir+'งานปัจจุบันของ ND — Current ND.md']=note('งานปัจจุบันของ ND','Current ND',order.map(o=>'- [['+owners[o][0]+' — '+owners[o][1]+']]').join('\n'),order.map(o=>'- [['+owners[o][0]+' — '+owners[o][1]+']]').join('\n'),'nd-graph-node');
const nodes=[{id:'root',type:'file',file:cdir+'งานปัจจุบันของ ND — Current ND.md',x:1000,y:0,width:390,height:170}],edges=[],xs=[0,360,720,1080,1440,1800,2160,2520];
for(let i=0;i<order.length;i++){
 const o=order[i],p=owners[o],oid='o'+i,of=cdir+p[0]+' — '+p[1]+'.md';
 nodes.push({id:oid,type:'file',file:of,x:xs[i],y:320,width:330,height:155});edges.push({id:'r-'+oid,fromNode:'root',toNode:oid,toEnd:'arrow',label:'delegates'});
 const ts=semantic.tasks.filter(t=>t.owner===o).slice(0,6);
 for(let j=0;j<ts.length;j++){const t=ts[j],id='t'+i+'-'+j;nodes.push({id:id,type:'text',text:'## '+t.title_th+'\n'+t.title_en+'\n\n**'+t.status+'**\n\n'+t.summary_th+'\n\n'+t.summary_en,x:xs[i],y:560+j*230,width:330,height:190});edges.push({id:oid+'-'+id,fromNode:oid,toNode:id,toEnd:'arrow',label:'owns'});}
}
files[cdir+'งานปัจจุบันของ ND — Current ND.canvas']=JSON.stringify({nodes:nodes,edges:edges},null,2)+'\n';
for(const p of Object.keys(files))if(p.endsWith('.md')&&!noCyr(files[p]))throw new Error('CYRILLIC_HUMAN_FILE:'+p);

const c=await commit(files,'state-refresh: overwrite ND state v'+ver+' '+started);
console.log(JSON.stringify({status:'PASS',run_id:run,state_version:ver,commit:c,semantic_refresh:semanticRefresh,model:model,head:authority.state_head.head_id,registry:authority.registry.version}));
})().catch(e=>{console.error('ND_STATE_REFRESH_FAILED',String(e&&e.stack?e.stack:e));process.exit(1);});
