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

// ND_RENDER_TO_VERCEL_PROBE_V1 — read-only cold gateway probe, no authentication or writes.
try { const probe=await fetch('https://nd-porfirchik-vk-gateway.vercel.app/api/health',{signal:AbortSignal.timeout(14000)}); const body=await probe.text(); console.log('ND_RENDER_TO_VERCEL_PROBE_V1',JSON.stringify({status:probe.status,body:body.slice(0,900)})); const test=await fetch('https://nd-porfirchik-vk-gateway.vercel.app/api/selftest',{signal:AbortSignal.timeout(14000)}); console.log('ND_RENDER_TO_VERCEL_SYNTHETIC_TEST',JSON.stringify({status:test.status,body:(await test.text()).slice(0,1200)})); } catch(error) { console.warn('ND_RENDER_TO_VERCEL_PROBE_V1',JSON.stringify({error:String(error).slice(0,250)})); }


// ND_VK_READONLY_QUALIFY_20261009 — bounded API probe, no mutations, keys, or private messages output.
try {
  const access=String(process.env.VK_GROUP_TOKEN||'').trim();
  async function vkRead(method,params={}) {
    const q=new URLSearchParams({...params,access_token:access,v:'5.199'});
    const response=await fetch('https://api.vk.com/method/'+method,{method:'POST',body:q,signal:AbortSignal.timeout(8500)});
    const data=await response.json();
    return {http:response.status,error:data.error?{code:data.error.error_code,message:String(data.error.error_msg||'').slice(0,120)}:null,response:data.response};
  }
  const identity=await vkRead('groups.getById',{group_ids:'228330620'});
  const gr=Array.isArray(identity.response)?identity.response[0]:identity.response?.groups?.[0]??identity.response;
  console.log('ND_VK_IDENTITY_DIAG',JSON.stringify({http:identity.http,error:identity.error,group_id:gr?.id??null,group_name:gr?.name??null}));
  const callbacks=await vkRead('groups.getCallbackServers',{group_id:'228330620'});
  const servers=Array.isArray(callbacks.response)?callbacks.response:callbacks.response?.items||[];
  console.log('ND_VK_CALLBACK_DIAG',JSON.stringify({http:callbacks.http,error:callbacks.error,server_count:callbacks.response?.count??servers.length,servers:servers.map(s=>({id:s.id,title:s.title,status:s.status,url:String(s.url||'').replace(/[0-9a-f]{32}/g,'[PATH-REDACTED]')}))}));
} catch (error) {
  console.log('ND_VK_DIAG_ERROR',JSON.stringify({type:error?.name||'Error'}));
}
