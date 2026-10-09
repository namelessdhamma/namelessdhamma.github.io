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



// ND_VK_CALLBACK_CUTOVER_VERIFY_V1 — idempotent, provider-verified retiring of offline Railway callback.
try {
 const token=String(process.env.VK_GROUP_TOKEN||'').trim();
 async function api(method,params){
  const q=new URLSearchParams({...params,access_token:token,v:'5.199'});
  const r=await fetch('https://api.vk.com/method/'+method,{method:'POST',body:q,signal:AbortSignal.timeout(9000)});
  const x=await r.json();
  if(!r.ok||x.error)throw Error(method+':'+(x.error?.error_code||r.status));
  return x.response;
 }
 const serversBefore=await api('groups.getCallbackServers',{group_id:'228330620'});
 const list=serversBefore.items||[];
 const current=list.find(x=>x.id===4 && x.status==='ok' && String(x.url||'').startsWith('https://nd-porfirchik-cold.onrender.com/vk/callback/'));
 const old=list.find(x=>x.id===3 && String(x.url||'').startsWith('https://nd-yandex-n8n-gateway-production.up.railway.app/'));
 let eventEnabled=false;
 if(current){
  const settings=await api('groups.getCallbackSettings',{group_id:'228330620',server_id:'4'});
  eventEnabled=Boolean(settings?.events?.message_new||settings?.events?.message_reply);
  console.log('ND_VK_CUTOVER_EVENTS',JSON.stringify({new_server:4,active:current.status,events_message_new:Boolean(settings?.events?.message_new),events_message_reply:Boolean(settings?.events?.message_reply)}));
 }
 let retired=false;
 if(current&&eventEnabled&&old) {
  await api('groups.deleteCallbackServer',{group_id:'228330620',server_id:'3'});
  retired=true;
 }
 const after=await api('groups.getCallbackServers',{group_id:'228330620'});
 console.log('ND_VK_CUTOVER_RESULT',JSON.stringify({new_active:!!current,events_enabled:eventEnabled,old_retired:retired,server_ids:(after?.items||[]).map(x=>({id:x.id,status:x.status,location:String(x.url||'').includes('onrender.com')?'render':String(x.url||'').includes('railway.app')?'railway':'other'}))}));
} catch(e) {
 console.log('ND_VK_CUTOVER_GUARD',JSON.stringify({error:String(e?.message||e).slice(0,150)}));
}


// ND_VK_OUTBOUND_SINGLE_TEST_20261009 — one bounded migration test to own operator account, never to father.
// No message text, tokens, or recipient names from private VK histories are logged.
try {
 if(Date.now()<Date.parse('2026-10-09T00:50:00Z')){
  const token=String(process.env.VK_GROUP_TOKEN||'').trim();
  const ask=async(method,p)=>{let q=new URLSearchParams({...p,access_token:token,v:'5.199'});let r=await fetch('https://api.vk.com/method/'+method,{method:'POST',body:q,signal:AbortSignal.timeout(9000)});return await r.json();};
  const users=await ask('users.get',{user_ids:'452972559,691392544'});
  const savva=(users.response||[]).filter(x=>/^(savva|савва)$/i.test(String(x.first_name||'')));
  console.log('ND_VK_OPERATOR_IDENTIFY',JSON.stringify({http_ok:!users.error,error_code:users.error?.error_code||null,operator_candidates:savva.map(x=>x.id),total:(users.response||[]).length}));
  if(savva.length===1){
   const test=await ask('messages.send',{user_id:String(savva[0].id),random_id:'20261009',message:'Техническая проверка Порфирчика: отправка сообщений через новую инфраструктуру Render. Действий не требуется.'});
   console.log('ND_VK_OPERATOR_OUTBOUND_TEST',JSON.stringify({ok:typeof test.response==='number',error_code:test.error?.error_code||null,message_sent_id:typeof test.response==='number'?test.response:null}));
  }
 }
} catch(e){console.log('ND_VK_OPERATOR_OUTBOUND_TEST',JSON.stringify({error_type:e?.name||'Error'}))}
