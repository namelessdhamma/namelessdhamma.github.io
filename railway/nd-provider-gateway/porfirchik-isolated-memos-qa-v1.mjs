// Migration continuity fixture, phase 2. Verify stored synthetic memory AFTER fresh Render deploy, then delete.
const key=String(process.env.MEMOS_API_KEY||'');
const base=String(process.env.MEMOS_CLOUD_URL||'https://memos.memtensor.cn/api/openmem/v1').replace(/\/+$/,'');
const user='nd-porfirchik-migration-proof-20261009';
const conversation='nd-isolated-restart';
const marker='ultramarine-continuity-9417';
const api=async(path,body)=>{
 const response=await fetch(base+path,{method:'POST',headers:{Authorization:'Token '+key,'Content-Type':'application/json',source:'porfirchik-vk'},body:JSON.stringify(body),signal:AbortSignal.timeout(10000)});
 const j=await response.json().catch(()=>({}));
 if(!response.ok||j.error)throw Error('memos_http_'+response.status);
 return j;
};
async function verify(){
 if(!key)return console.log('ND_MEMOS_RESTART_QA',JSON.stringify({phase:'AFTER_RESTART',ok:false,reason:'not_configured'}));
 try{
  for(let attempt=1;attempt<=3;attempt++){
   const obj=await api('/search/memory',{user_id:user,conversation_id:conversation,query:'What was the synthetic continuity test marker?',memory_limit_number:20,include_preference:true,preference_limit_number:4,include_tool_memory:false,include_skill:true,skill_limit_number:4,relativity:0.0});
   const root=obj.data||obj,items=['memory_detail_list','preference_detail_list','skill_detail_list','skill_list'].flatMap(k=>Array.isArray(root[k])?root[k]:[]);
   const found=items.filter(v=>JSON.stringify(v).includes(marker));
   if(found.length){
    console.log('ND_MEMOS_RESTART_QA',JSON.stringify({phase:'AFTER_RESTART',ok:true,persisted:true,match_count:found.length,attempt}));
    const ids=[...new Set(found.map(x=>x.memory_id||x.id||x._id).filter(Boolean).map(String))];
    if(ids.length){
     try{await api('/delete/memory',{memory_ids:ids});console.log('ND_MEMOS_RESTART_QA',JSON.stringify({phase:'CLEANUP',ok:true,deleted_count:ids.length}));}
     catch(e){console.log('ND_MEMOS_RESTART_QA',JSON.stringify({phase:'CLEANUP',ok:false,error:String(e.message||e).slice(0,40)}))}
    }else console.log('ND_MEMOS_RESTART_QA',JSON.stringify({phase:'CLEANUP',ok:false,reason:'no_ids'}));
    return;
   }
   if(attempt<3)await new Promise(r=>setTimeout(r,10000));
  }
  console.log('ND_MEMOS_RESTART_QA',JSON.stringify({phase:'AFTER_RESTART',ok:false,persisted:false}));
 }catch(e){console.log('ND_MEMOS_RESTART_QA',JSON.stringify({phase:'ERROR',error:String(e.message||e).slice(0,65)}))}
}
setTimeout(()=>void verify(),12000).unref();