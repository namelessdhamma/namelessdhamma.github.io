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

// Non-blocking encrypted archive sidecar; core VK traffic remains unchanged.
try { await import('./porfirchik-memory-archive-v1.mjs'); }
catch (e) { console.error('ND_ARCHIVE_SIDECAR_FAILED',String(e?.name||'Error')); }


// ND_VK_RESTORE_HISTORY_COUNTS_20261009 — read-only metadata counts, no message text.
try{
 const t=String(process.env.VK_GROUP_TOKEN||'').trim();
 for (const peer of [452972559,691392544]) {
  const q=new URLSearchParams({access_token:t,v:'5.199',peer_id:String(peer),count:'1'});
  const res=await fetch('https://api.vk.com/method/messages.getHistory',{method:'POST',body:q,signal:AbortSignal.timeout(7000)});
  const d=await res.json();
  console.log('ND_VK_HISTORY_COUNT',JSON.stringify({peer_id:peer,http:res.status,error:d.error?.error_code||null,count:d.response?.count??null,items:d.response?.items?.length??0}));
 }
}catch(e){console.log('ND_VK_HISTORY_COUNT',JSON.stringify({error_type:e?.name||'Error'}))}
