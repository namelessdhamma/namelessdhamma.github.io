// Porfirchik free-tier safe archive v1. Encrypted SQLite snapshots -> signed private Vercel Blob receiver.
// Never exposes VK credentials, database plaintext, or derived decryption keys to the receiver.
import crypto from 'node:crypto';
import {promisify} from 'node:util';
import {execFile} from 'node:child_process';
const run=promisify(execFile);
const token=String(process.env.VK_GROUP_TOKEN||'').trim();
const db=String(process.env.PORFIRCHIK_MEMOS_LOCAL_DB||'/tmp/porfirchik-memos.sqlite3').trim();
const endpoint='https://nd-porfirchik-vk-gateway.vercel.app/api/archive';
const seed=crypto.createHash('sha256').update('nd-porfirchik-archive-signing-v1:'+token).digest();
const privateKey=token?crypto.createPrivateKey({key:Buffer.concat([Buffer.from('302e020100300506032b657004220420','hex'),seed]),format:'der',type:'pkcs8'}):null;
const aesKey=crypto.createHash('sha256').update('nd-porfirchik-archive-data-v1:'+token).digest();
let busy=false,lastPlainHash='';
const py=String.raw`import sqlite3, tempfile, os, gzip, base64, json, sys
p=sys.argv[1]
if not os.path.isfile(p):
 print(json.dumps({'skip':'missing'}));sys.exit(0)
dest=tempfile.NamedTemporaryFile(prefix='nd-pfm-',suffix='.sqlite3',delete=False)
t=dest.name;dest.close()
try:
 src=sqlite3.connect('file:'+p+'?mode=ro',uri=True,timeout=5)
 dst=sqlite3.connect(t)
 src.backup(dst,pages=256,sleep=0.02)
 dst.commit()
 try: n=int(dst.execute('select count(*) from porfirchik_memory').fetchone()[0])
 except sqlite3.Error: n=0
 dst.close();src.close()
 if n<1:print(json.dumps({'skip':'empty','count':n}));sys.exit(0)
 raw=open(t,'rb').read()
 zipped=gzip.compress(raw,compresslevel=7)
 if len(zipped)>2100000:print(json.dumps({'skip':'oversized','compressed_bytes':len(zipped)}));sys.exit(0)
 print(json.dumps({'count':n,'zipped':base64.b64encode(zipped).decode('ascii')}))
finally:
 try:os.unlink(t)
 except OSError:pass`;
async function archive(){
 if(busy||!token||!privateKey)return;
 busy=true;
 try{
  const {stdout}=await run('python3',['-c',py,db],{timeout:16000,maxBuffer:3200000,env:{...process.env,PYTHONUNBUFFERED:'1'}});
  const obj=JSON.parse(stdout.trim());
  if(obj.skip){console.log('ND_ARCHIVE_SKIP',JSON.stringify({reason:obj.skip,count:obj.count??null}));return}
  const plain=Buffer.from(obj.zipped,'base64');
  const fingerprint=crypto.createHash('sha256').update(plain).digest('hex');
  if(fingerprint===lastPlainHash)return;
  const nonce=crypto.randomBytes(12);
  const cipher=crypto.createCipheriv('aes-256-gcm',aesKey,nonce);
  const encrypted=Buffer.concat([cipher.update(plain),cipher.final()]);
  const tag=cipher.getAuthTag();
  const envelope={version:1,ts:Date.now(),sha256:crypto.createHash('sha256').update(encrypted).digest('hex'),nonce:nonce.toString('base64'),tag:tag.toString('base64'),ciphertext:encrypted.toString('base64')};
  const canon=[envelope.version,envelope.ts,envelope.sha256,envelope.nonce,envelope.tag,envelope.ciphertext].join('\n');
  const sig=crypto.sign(null,Buffer.from(canon,'utf-8'),privateKey).toString('base64');
  const response=await fetch(endpoint,{method:'POST',headers:{'content-type':'application/json','x-nd-archive-sig':sig},body:JSON.stringify(envelope),signal:AbortSignal.timeout(16000)});
  const result=await response.json().catch(()=>({}));
  if(response.status!==201||!result.ok||!result.verified_head||result.sha256!==envelope.sha256)throw Error('receiver_qualification_failed_'+response.status+'_'+String(result?.error||'unknown'));
  lastPlainHash=fingerprint;
  console.log('ND_ARCHIVE_VERIFIED',JSON.stringify({records:obj.count,compressed_bytes:plain.length,sha256:envelope.sha256,stored:true,readback:true,storage:'vercel-private-blob'}));
 }catch(e){console.log('ND_ARCHIVE_FAILED',JSON.stringify({type:e?.name||'Error',reason:String(e?.message||'').slice(0,140)}))}
 finally{busy=false}
}
if(token){
 setTimeout(()=>void archive(),60000).unref();
 setInterval(()=>void archive(),7*60000).unref();
 console.log('ND_ARCHIVE_SCHEDULED',JSON.stringify({encrypted:true,receiver:'vercel_private_blob',period_minutes:7}));
}else console.log('ND_ARCHIVE_DISABLED',JSON.stringify({reason:'vk_token_missing'}));
