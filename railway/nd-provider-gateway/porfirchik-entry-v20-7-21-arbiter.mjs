import fs from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';

const here=path.dirname(fileURLToPath(import.meta.url));
const sourcePath=path.join(here,'server.mjs');
const runtimePath=path.join(here,'server.porfirchik-v20-7-21-arbiter.mjs');
let s=fs.readFileSync(sourcePath,'utf8');
const replaceOne=(from,to,label)=>{const n=s.split(from).length-1;if(n!==1)throw new Error('Porfirchik V20.7.21 activation anchor mismatch: '+label+' count='+n);s=s.replace(from,to);};
replaceOne(
  "const ND_PORFIRCHIK_GATEWAY_V20_7_4='porfirchik-v20.7.4-free-music-yandex-fallback-20260930';",
  "const ND_PORFIRCHIK_GATEWAY_V20_7_4='porfirchik-v20.7.21-arbiter-fencing-20261002';",
  'revision'
);
replaceOne(
  "const PORFIRCHIK_SOURCE_COMMIT='9b7da70f9e05188966d52c73f5b55d772267006a';",
  "const PORFIRCHIK_SOURCE_COMMIT='4c1453183601fc3fabc6bbb807a6ef66153078b2';",
  'source_commit'
);
replaceOne(
  "const PORFIRCHIK_SOURCE_PATH='tmp/nd_vk_v20_7_4_music_yandex_fallback_loader.py';",
  "const PORFIRCHIK_SOURCE_PATH='tmp/nd_vk_v20_7_21_arbiter_fencing_loader.py';",
  'source_path'
);
replaceOne(
  "for(const key of ['CEREBRAS_API_KEY','MISTRAL_API_KEY','OPENAI_API_KEY','ZAI_API_KEY','OMNIROUTE_BASE_URL']){",
  "for(const key of ['OPENAI_API_KEY','OMNIROUTE_BASE_URL']){",
  'restore_historical_free_provider_env'
);
fs.writeFileSync(runtimePath,s);
console.log('ND_PORFIRCHIK_V20_7_21_ARBITER_ACTIVATION_SHIM_READY');
await import(pathToFileURL(runtimePath).href);


// ND_MEMOS_ISOLATED_VALIDATION_20261009 — one synthetic agent-only memory, no VK/father content.
setTimeout(async()=>{
 const key=String(process.env.MEMOS_API_KEY||'').trim(),base=String(process.env.MEMOS_CLOUD_URL||'https://memos.memtensor.cn/api/openmem/v1').replace(/\/+$/,'');
 if(!key)return console.log('ND_MEMOS_ISOLATED_TEST',JSON.stringify({ok:false,reason:'key_missing'}));
 const id='nd-porfirchik-independent-memory-qualification-20261009';
 const marker='zephyr-celadon-7319';
 const post=async(p,obj)=>{
   const response=await fetch(base+p,{method:'POST',headers:{Authorization:'Token '+key,'content-type':'application/json',source:'porfirchik-vk', 'User-Agent':'nd-porfirchik-migration-check'},body:JSON.stringify(obj),signal:AbortSignal.timeout(14000)});
   const body=await response.json().catch(()=>({}));
   return {http:response.status,code:body.code??null,success:body.success??null,body};
 };
 try{
   const add=await post('/add/message',{user_id:id,conversation_id:'synthetic-probe-20261009',agent_id:'porfirchik-qa-only',app_id:'porfirchik-migration-check',messages:[{role:'user',content:'Synthetic QA only: remember marker '+marker+'. No relation to any real user.'},{role:'assistant',content:'For this isolated QA profile, the test marker is '+marker+'.'}],tags:['diagnostic','isolated','not-father'],info:{source:'synthetic-qualification',memory_mode:'automatic'},allow_public:false,async_mode:true});
   console.log('ND_MEMOS_ISOLATED_ADD',JSON.stringify({http:add.http,accepted:add.http>=200&&add.http<300,code:add.code,success:add.success}));
   if(!(add.http>=200&&add.http<300))return;
   for(let attempt=1;attempt<=4;attempt++){
     await new Promise(resolve=>setTimeout(resolve,15000));
     const got=await post('/search/memory',{user_id:id,conversation_id:'synthetic-probe-20261009',query:'What is the synthetic QA marker?',memory_limit_number:12,include_preference:true,preference_limit_number:3,include_tool_memory:false,include_skill:true,skill_limit_number:3,relativity:0.2});
     const root=got.body?.data||got.body||{};
     const memories=[...(root.memory_detail_list||[]),...(root.preference_detail_list||[]),...(root.skill_detail_list||[])];
     const found=memories.some(o=>JSON.stringify(o).includes(marker));
     console.log('ND_MEMOS_ISOLATED_SEARCH',JSON.stringify({attempt,http:got.http,success:got.http>=200&&got.http<300,returned:memories.length,marker_found:found,code:got.code}));
     if(found)break;
   }
 }catch(e){console.log('ND_MEMOS_ISOLATED_TEST',JSON.stringify({exception:e?.name||'Error'}))}
},15000).unref();
