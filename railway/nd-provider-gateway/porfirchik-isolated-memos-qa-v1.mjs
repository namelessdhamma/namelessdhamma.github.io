// One-shot synthetic MemOS continuity qualification; no VK messages or personal data.
import {randomUUID} from 'node:crypto';
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function run(){
 const key=String(process.env.MEMOS_API_KEY||'');
 if(!key){console.log('ND_MEMOS_QA',JSON.stringify({phase:'SKIP',reason:'not_configured'}));return}
 const base=String(process.env.MEMOS_CLOUD_URL||'https://memos.memtensor.cn/api/openmem/v1').replace(/\/+$/,'');
 const uid='nd-qa-isolated-'+randomUUID();
 const marker='qualification-'+randomUUID().slice(0,15);
 const headers={Authorization:'Token '+key,'content-type':'application/json','User-Agent':'nd-porfirchik-isolated-qa-v1',source:'porfirchik-vk'};
 const api=async(path,obj)=>{
  const res=await fetch(base+path,{method:'POST',headers,body:JSON.stringify(obj),signal:AbortSignal.timeout(11000)});
  const data=await res.json().catch(()=>({}));
  if(!res.ok||data.error)throw Error('memos_http_'+res.status);
  return data;
 };
 try {
  await api('/add/message',{
   user_id:uid,conversation_id:'qa-'+uid,agent_id:'porfirchik-qa',app_id:'porfirchik-qa',
   messages:[{role:'user',content:'Synthetic test. My test marker is '+marker+'.'},{role:'assistant',content:'I will remember that synthetic marker '+marker+'.'}],
   tags:['migration_qa','synthetic','temporary'],info:{source:'isolated-migration-validation',memory_mode:'automatic'},allow_public:false,async_mode:true
  });
  console.log('ND_MEMOS_QA',JSON.stringify({phase:'ADD_ACCEPTED',isolated:true}));
  let found=false,cleanup=false,attempt=0;
  for(const ms of [8000,14000,22000,30000]){
   await delay(ms);
   attempt++;
   const obj=await api('/search/memory',{user_id:uid,conversation_id:'qa-'+uid,query:'What is the synthetic test marker?',memory_limit_number:20,include_preference:true,preference_limit_number:4,include_tool_memory:false,include_skill:true,skill_limit_number:4,relativity:0.0});
   const root=obj.data||obj;const keys=['memory_detail_list','preference_detail_list','skill_detail_list','skill_list'];
   const entries=keys.flatMap(k=>Array.isArray(root[k])?root[k]:[]);
   const tagged=entries.filter(x=>JSON.stringify(x).includes(marker));
   found=tagged.length>0;
   console.log('ND_MEMOS_QA',JSON.stringify({phase:'SEARCH',attempt,found,results:entries.length}));
   if(found){
    const ids=[...new Set(tagged.map(x=>x.memory_id||x.id||x._id).filter(Boolean).map(String))];
    if(ids.length){try{await api('/delete/memory',{memory_ids:ids});cleanup=true;}catch{cleanup=false}}
    console.log('ND_MEMOS_QA',JSON.stringify({phase:'END',ok:true,isolated:true,cleanup,delete_attempted:ids.length>0}));
    return;
   }
  }
  console.log('ND_MEMOS_QA',JSON.stringify({phase:'END',ok:false,reason:'not_indexed_in_window',attempts:attempt}));
 } catch(e){console.log('ND_MEMOS_QA',JSON.stringify({phase:'ERROR',reason:String(e.message||e).slice(0,65)}))}
}
setTimeout(()=>void run(),11000).unref();
console.log('ND_MEMOS_QA_BOOTSTRAP',JSON.stringify({safe_nonblocking:true,synthetic_only:true}));