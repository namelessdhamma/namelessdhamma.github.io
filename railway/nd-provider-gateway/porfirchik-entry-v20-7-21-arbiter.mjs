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
// ND_MEMOS_IDENTITY_CONFIGURATION_CHECK_20261009
console.log('ND_MEMOS_IDENTITY_CONFIG_CHECK', JSON.stringify({
  api_key_present: Boolean(process.env.MEMOS_API_KEY),
  user_salt_present: Boolean(process.env.MEMOS_USER_SALT),
  user_prefix_configured: Boolean(process.env.MEMOS_USER_PREFIX),
  agent_id_configured: Boolean(process.env.MEMOS_AGENT_ID),
  app_id_configured: Boolean(process.env.MEMOS_APP_ID),
  cloud_url_configured: Boolean(process.env.MEMOS_CLOUD_URL),
  // For migration continuity, compare with the historical Railway variable *names*; no secret values logged.
  values_redacted: true
}));

console.log('ND_PORFIRCHIK_V20_7_21_ARBITER_ACTIVATION_SHIM_READY');
await import(pathToFileURL(runtimePath).href);



// ND_MEMOS_READ_ONLY_LEGACY_PROFILE_PROBE_20261009
// Temporary bounded read-only recovery proof. Never print user text, snippets, tokens or memory values.
setTimeout(async()=>{
  try {
    const {createHash}=await import('node:crypto');
    const token=String(process.env.MEMOS_API_KEY||'').trim();
    const salt=String(process.env.MEMOS_USER_SALT||'');
    const prefix=String(process.env.MEMOS_USER_PREFIX||'porfirchik');
    const endpoint=String(process.env.MEMOS_CLOUD_URL||'https://memos.memtensor.cn/api/openmem/v1').replace(/\/+$/,'')+'/search/memory';
    const ids=[452972559,691392544];
    if(!token||!salt){console.log('ND_MEMOS_LEGACY_PROBE',JSON.stringify({ok:false,reason:'missing_credentials'}));return}
    for(let i=0;i<ids.length;i++){
      const uid=ids[i],hashed=createHash('sha256').update(String(uid)+'|'+salt).digest('hex').slice(0,20);
      const user=prefix+'-'+hashed;
      const summary={slot:i+1,authenticated:false,queries:0,total_matches:0,cloud_errors:0};
      for(const q of ['книга стихи произведения музыка','общение семья учение запомни']) {
        try{
          const b={user_id:user,conversation_id:'vk-'+uid,query:q,memory_limit_number:20,include_preference:true,preference_limit_number:8,include_tool_memory:false,include_skill:true,skill_limit_number:8,relativity:0.0};
          const response=await fetch(endpoint,{method:'POST',headers:{Authorization:'Token '+token,'Content-Type':'application/json',source:'porfirchik-vk'},body:JSON.stringify(b),signal:AbortSignal.timeout(7000)});
          const body=await response.json().catch(()=>({}));
          const root=body?.data??body;
          const n=['memory_detail_list','preference_detail_list','skill_detail_list','skill_list'].reduce((acc,k)=>acc+(Array.isArray(root?.[k])?root[k].length:0),0);
          summary.queries++;summary.authenticated=summary.authenticated||(response.ok&&!body.error);summary.total_matches+=n;if(!response.ok||body.error)summary.cloud_errors++;
        }catch(e){summary.cloud_errors++}
      }
      console.log('ND_MEMOS_LEGACY_PROBE',JSON.stringify(summary));
    }
  }catch(e){console.log('ND_MEMOS_LEGACY_PROBE',JSON.stringify({ok:false,error_type:String(e?.name||'Error')}))}
},9000).unref();
