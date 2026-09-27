const API='https://cloud-api.yandex.net/v1/disk';
const TOKEN=String(process.env.YANDEX_DISK_TOKEN||'').trim();
if(!TOKEN) throw new Error('YANDEX_DISK_TOKEN missing');

const headers={Authorization:'OAuth '+TOKEN,Accept:'application/json','User-Agent':'nd-yandex-blue-sea-share/1.0'};

async function request(endpoint, query={}, method='GET', body=null){
  const u=new URL(API+endpoint);
  for(const [k,v] of Object.entries(query)) if(v!==undefined&&v!==null) u.searchParams.set(k,String(v));
  const h={...headers};
  const opts={method,headers:h};
  if(body!==null){h['Content-Type']='application/json';opts.body=JSON.stringify(body);}
  const r=await fetch(u,opts);
  const t=await r.text();
  let d={};
  if(t){try{d=JSON.parse(t);}catch{d={text:t.slice(0,2000)};}}
  return {ok:r.ok,status:r.status,data:d};
}
async function must(endpoint, query={}, method='GET', body=null){
  const r=await request(endpoint,query,method,body);
  if(!r.ok) throw new Error(method+' '+endpoint+' HTTP '+r.status+': '+(r.data.message||r.data.description||r.data.text||'request_failed'));
  return r.data;
}
async function publishEditable(path){
  const publishBody={public_settings:{accesses:[{macros:['all'],rights:['write']}]}};
  let r=await request('/resources/publish',{path,allow_address_access:'true'},'PUT',publishBody);
  if(!r.ok && r.status!==409){
    // Fallback for accounts that accept basic publication first, then settings mutation.
    r=await request('/resources/publish',{path},'PUT',null);
    if(!r.ok && r.status!==409) throw new Error('publish HTTP '+r.status+': '+(r.data.message||r.data.description||'request_failed'));
  }

  const settingsBody={accesses:[{type:'macro',macros:['all'],rights:['write']}]};
  const s=await request('/public/resources/public-settings',{path,allow_address_access:'true'},'PATCH',settingsBody);
  if(!s.ok) throw new Error('settings PATCH HTTP '+s.status+': '+(s.data.message||s.data.description||s.data.text||'request_failed'));

  const v=await must('/public/resources/public-settings',{path,allow_address_access:'true'});
  const macro=(v.accesses||[]).find(x=>x&&x.type==='macro'&&Array.isArray(x.macros)&&x.macros.includes('all'));
  if(!macro||!Array.isArray(macro.rights)||!macro.rights.includes('write')) throw new Error('write/all verification failed');

  const meta=await must('/resources',{path,fields:'name,path,public_url,public_key'});
  if(!meta.public_url) throw new Error('public_url missing');
  return meta.public_url;
}
async function uploadText(path,text,contentType){
  const d=await must('/resources/upload',{path,overwrite:'true'});
  if(!d.href) throw new Error('upload href missing for '+path);
  const r=await fetch(d.href,{method:'PUT',headers:{'Content-Type':contentType},body:Buffer.from(text,'utf8')});
  if(!r.ok) throw new Error('upload HTTP '+r.status+' for '+path);
}

const items=[];
for(let i=1;i<=108;i++){
  const n=String(i).padStart(3,'0');
  items.push({episode:i,kind:'draft',path:'disk:/Синее море/Сценарий черновики/'+n+'_Эпизод '+i+'_черновик.docx'});
  items.push({episode:i,kind:'final',path:'disk:/Синее море/Сценарий чистовики/'+n+'_Эпизод '+i+'.docx'});
}

const results=new Array(items.length);
const errors=[];
let next=0, done=0;
async function worker(){
  while(true){
    const idx=next++;
    if(idx>=items.length) return;
    const item=items[idx];
    try{
      const public_url=await publishEditable(item.path);
      results[idx]={...item,public_url};
      done++;
      if(done%12===0||done===items.length) console.log('BLUE_SEA_SHARE_PROGRESS',JSON.stringify({done,total:items.length}));
    }catch(e){
      errors.push({episode:item.episode,kind:item.kind,path:item.path,error:String(e&&e.message||e).slice(0,800)});
    }
  }
}
await Promise.all([worker(),worker(),worker()]);

if(errors.length){
  console.error('BLUE_SEA_SHARE_ERRORS',JSON.stringify(errors));
  throw new Error('Blue Sea share batch failed: '+errors.length+' errors');
}

const episodes=[];
for(let i=1;i<=108;i++){
  const d=results.find(x=>x.episode===i&&x.kind==='draft');
  const f=results.find(x=>x.episode===i&&x.kind==='final');
  episodes.push({
    episode:i,
    draft_url:d.public_url,
    final_url:f.public_url,
    draft_path:d.path,
    final_path:f.path,
    rights:'write',
    access:'all'
  });
}

const manifest={
  project:'Синее море',
  generated_at:new Date().toISOString(),
  count:108,
  files:216,
  rights:'write',
  access:'all',
  episodes
};
await uploadText('disk:/Синее море/share_links.json',JSON.stringify(manifest,null,2),'application/json; charset=utf-8');

let toc='# Синее море — сценарий\n\n';
for(const x of episodes){
  toc+='Эпизод '+x.episode+'\n';
  toc+='Черновик: '+x.draft_url+'\n';
  toc+='Чистовик: '+x.final_url+'\n\n';
}
await uploadText('disk:/Синее море/Оглавление.md',toc,'text/markdown; charset=utf-8');

console.log('BLUE_SEA_SHARE_COMPLETE',JSON.stringify({episodes:108,files:216,rights:'write',access:'all'}));
