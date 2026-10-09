// Migration continuity fixture, phase 1. Synthetic dedicated user. No VK or personal data.
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
async function first(){
 if(!key)return console.log('ND_MEMOS_RESTART_QA',JSON.stringify({phase:'PREPARE',ok:false,reason:'not_configured'}));
 try{
  const payload={user_id:user,conversation_id:conversation,agent_id:'porfirchik-qa',app_id:'porfirchik-qa',
   messages:[{role:'user',content:'Synthetic continuity test marker: '+marker},{role:'assistant',content:'I remember the synthetic marker '+marker}],tags:['temporary','continuity_qa'],info:{source:'isolated-migration-continuity',memory_mode:'automatic'},allow_public:false,async_mode:true};
  await api('/add/message',payload);
  console.log('ND_MEMOS_RESTART_QA',JSON.stringify({phase:'ADD_BEFORE_RESTART',ok:true}));
  await new Promise(r=>setTimeout(r,9000));
  const obj=await api('/search/memory',{user_id:user,conversation_id:conversation,query:'What was the synthetic continuity test marker?',memory_limit_number:20,include_preference:true,preference_limit_number:4,include_tool_memory:false,include_skill:true,skill_limit_number:4,relativity:0.0});
  const root=obj.data||obj;const items=['memory_detail_list','preference_detail_list','skill_detail_list','skill_list'].flatMap(k=>Array.isArray(root[k])?root[k]:[]);
  console.log('ND_MEMOS_RESTART_QA',JSON.stringify({phase:'SEARCH_BEFORE_RESTART',ok:items.some(v=>JSON.stringify(v).includes(marker)),count:items.length}));
 }catch(e){console.log('ND_MEMOS_RESTART_QA',JSON.stringify({phase:'ERROR',error:String(e.message||e).slice(0,65)}))}
}
setTimeout(()=>void first(),9000).unref();