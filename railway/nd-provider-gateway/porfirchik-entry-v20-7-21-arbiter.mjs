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


// ND_CLOUDFLARE_KV_PERMISSION_PROBE_20261009
// Read-only inquiry into whether configured Cloudflare API token supports secure durable KV archives.
try {
 const account=String(process.env.CLOUDFLARE_ACCOUNT_ID||'').trim();
 const token=String(process.env.CLOUDFLARE_API_TOKEN||'').trim();
 if(account && token) {
  const u='https://api.cloudflare.com/client/v4/accounts/'+encodeURIComponent(account)+'/storage/kv/namespaces?per_page=20';
  const r=await fetch(u,{headers:{Authorization:'Bearer '+token},signal:AbortSignal.timeout(8000)});
  const o=await r.json();
  console.log('ND_CLOUDFLARE_KV_READ_DIAG',JSON.stringify({http:r.status,success:!!o.success,error_codes:(o.errors||[]).map(x=>x.code),namespaces:(o.result||[]).map(x=>({id:x.id,title:x.title}))}));
 } else console.log('ND_CLOUDFLARE_KV_READ_DIAG',JSON.stringify({configured:false}));
} catch(e){console.log('ND_CLOUDFLARE_KV_READ_DIAG',JSON.stringify({error_type:String(e?.name||'Error')}))}
