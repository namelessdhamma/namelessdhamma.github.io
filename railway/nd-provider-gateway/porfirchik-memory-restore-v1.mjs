// Nonblocking recoverable-memory merge from signed Vercel Private Blob.
// Retrieves ciphertext only after Ed25519 proof, decrypts locally, merges in SQLite transaction.
import crypto from 'node:crypto';
import fs from 'node:fs/promises';
import zlib from 'node:zlib';
import {promisify} from 'node:util';
import {execFile} from 'node:child_process';
const exec=promisify(execFile);
const tok=String(process.env.VK_GROUP_TOKEN||'').trim();
const db=String(process.env.PORFIRCHIK_MEMOS_LOCAL_DB||'/tmp/porfirchik-memos.sqlite3').trim();
const seed=crypto.createHash('sha256').update('nd-porfirchik-archive-signing-v1:'+tok).digest();
const privateKey=tok?crypto.createPrivateKey({key:Buffer.concat([Buffer.from('302e020100300506032b657004220420','hex'),seed]),format:'der',type:'pkcs8'}):null;
const aesKey=crypto.createHash('sha256').update('nd-porfirchik-archive-data-v1:'+tok).digest();
const py=String.raw`import sqlite3,sys,json
active=sys.argv[1];snapshot=sys.argv[2]
c=sqlite3.connect(active,timeout=12)
c.execute('PRAGMA busy_timeout=12000')
c.execute('PRAGMA journal_mode=WAL')
c.execute('ATTACH DATABASE ? AS archive',(snapshot,))
exists=lambda table:bool(c.execute('SELECT 1 FROM archive.sqlite_master WHERE type="table" AND name=?',(table,)).fetchone())
details={'ok':True,'old_memories_found':0,'memories_added':0,'history_found':0,'history_added':0}
try:
 if exists('porfirchik_memory'):
  c.execute("""CREATE TABLE IF NOT EXISTS porfirchik_memory(
  id INTEGER PRIMARY KEY AUTOINCREMENT,uid TEXT NOT NULL,ts INTEGER NOT NULL,user_text TEXT NOT NULL,
  assistant_text TEXT NOT NULL,weight REAL NOT NULL DEFAULT 1.0,tags TEXT NOT NULL DEFAULT '')""")
  r=c.execute('SELECT uid,ts,user_text,assistant_text,weight,tags FROM archive.porfirchik_memory ORDER BY id').fetchall()
  details['old_memories_found']=len(r)
  for row in r:
   same=c.execute('SELECT 1 FROM porfirchik_memory WHERE uid=? AND ts=? AND user_text=? AND assistant_text=? LIMIT 1',(row[0],row[1],row[2],row[3])).fetchone()
   if not same:
    c.execute('INSERT INTO porfirchik_memory(uid,ts,user_text,assistant_text,weight,tags) VALUES(?,?,?,?,?,?)',row)
    details['memories_added']+=1
 if exists('porfirchik_vk_history'):
  c.execute("""CREATE TABLE IF NOT EXISTS porfirchik_vk_history(
  peer_id INTEGER NOT NULL,message_id INTEGER NOT NULL,date INTEGER NOT NULL,from_id INTEGER NOT NULL,
  outgoing INTEGER NOT NULL,message_text TEXT NOT NULL,source_json TEXT NOT NULL,
  PRIMARY KEY(peer_id,message_id))""")
  details['history_found']=int(c.execute('SELECT COUNT(*) FROM archive.porfirchik_vk_history').fetchone()[0])
  c.execute('INSERT OR IGNORE INTO porfirchik_vk_history(peer_id,message_id,date,from_id,outgoing,message_text,source_json) SELECT peer_id,message_id,date,from_id,outgoing,message_text,source_json FROM archive.porfirchik_vk_history')
  details['history_added']=int(c.execute('SELECT changes()').fetchone()[0])
 c.commit()
 print(json.dumps(details))
except Exception:
 c.rollback()
 raise
finally:
 c.close()`;
async function restore(){
 if(!privateKey)return;
 let tmp='';
 try{
  const ts=Date.now(),nonce=crypto.randomBytes(16).toString('base64');
  const canon=['nd-porfirchik-archive-recover-v1',ts,nonce].join('\n');
  const sig=crypto.sign(null,Buffer.from(canon),privateKey).toString('base64');
  const r=await fetch('https://nd-porfirchik-vk-gateway.vercel.app/api/archive-recover',{method:'POST',headers:{'content-type':'application/json','x-nd-archive-sig':sig},body:JSON.stringify({ts,nonce}),signal:AbortSignal.timeout(16000)});
  const out=await r.json();
  if(r.status===404){console.log('ND_ARCHIVE_RESTORE_SKIP',JSON.stringify({reason:'no_snapshot'}));return}
  if(!r.ok||!out.ok||!out.encrypted||!out.archive)throw Error('receiver_'+r.status+'_'+String(out.error||'unknown'));
  const b=out.archive;
  const cipher=Buffer.from(b.ciphertext||'','base64');
  if(crypto.createHash('sha256').update(cipher).digest('hex')!==b.sha256)throw Error('archive_ciphertext_hash');
  const nonceBuf=Buffer.from(b.nonce||'','base64'),tag=Buffer.from(b.tag||'','base64');
  if(nonceBuf.length!==12||tag.length!==16||cipher.length>2400000)throw Error('archive_envelope');
  const decipher=crypto.createDecipheriv('aes-256-gcm',aesKey,nonceBuf);decipher.setAuthTag(tag);
  const zipped=Buffer.concat([decipher.update(cipher),decipher.final()]);
  const raw=zlib.gunzipSync(zipped,{maxOutputLength:30000000});
  if(raw.subarray(0,16).toString('utf8')!=='SQLite format 3\u0000')throw Error('not_sqlite_snapshot');
  tmp='/tmp/nd-pfm-restore-'+String(process.pid)+'-'+String(Date.now())+'.sqlite3';
  await fs.writeFile(tmp,raw,{mode:0o600,flag:'wx'});
  const {stdout}=await exec('python3',['-c',py,db,tmp],{timeout:20000,maxBuffer:30000});
  const res=JSON.parse(stdout.trim());
  if(!res.ok)throw Error('sqlite_merge_failed');
  console.log('ND_ARCHIVE_RESTORED',JSON.stringify({verified:true,encrypted:true,...res}));
 }catch(e){console.log('ND_ARCHIVE_RESTORE_FAILED',JSON.stringify({type:e?.name||'Error',reason:String(e?.message||'').slice(0,140)}))}
 finally{if(tmp)await fs.unlink(tmp).catch(()=>{})}
}
if(tok){setTimeout(()=>void restore(),18000).unref();console.log('ND_ARCHIVE_RESTORE_SCHEDULED',JSON.stringify({mode:'nonblocking_merge',receiver:'vercel_private_blob'}))}
