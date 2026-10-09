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

// ND_PORFIRCHIK_ARCHIVE_PUBLIC_KEY_20261009 — public identifier only, no secrets or backups sent.
try{
 const crypto=await import('node:crypto');
 const tok=String(process.env.VK_GROUP_TOKEN||'').trim();
 if(tok){
  const seed=crypto.createHash('sha256').update('nd-porfirchik-archive-signing-v1:'+tok).digest();
  const der=Buffer.concat([Buffer.from('302e020100300506032b657004220420','hex'),seed]);
  const priv=crypto.createPrivateKey({key:der,format:'der',type:'pkcs8'});
  const pub=crypto.createPublicKey(priv).export({format:'der',type:'spki'}).toString('base64');
  console.log('ND_PORFIRCHIK_ARCHIVE_PUBLIC_KEY',JSON.stringify({algorithm:'ed25519',spki_base64:pub}));
 }
}catch(e){console.log('ND_PORFIRCHIK_ARCHIVE_PUBLIC_KEY',JSON.stringify({error_type:e?.name||'Error'}))}
