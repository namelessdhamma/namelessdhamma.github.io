// One-shot, read-only VK message history recovery into a *separate* SQLite table.
// No outbound VK messages, no changes to Porfirchik generated-memory table.
import fs from 'node:fs/promises';
import {promisify} from 'node:util';
import {execFile} from 'node:child_process';
const execute=promisify(execFile);
const token=String(process.env.VK_GROUP_TOKEN||'').trim();
const db=String(process.env.PORFIRCHIK_MEMOS_LOCAL_DB||'/tmp/porfirchik-memos.sqlite3').trim();
const peers=[452972559,691392544];
const allow=new Set(String(process.env.VK_ALLOWED_USER_IDS||'').split(/[,;\s]+/).filter(Boolean).map(Number));
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const python=String.raw`import json,sqlite3,sys
db=sys.argv[1];payload=sys.argv[2]
rows=json.load(open(payload,encoding='utf-8'))
c=sqlite3.connect(db,timeout=12)
c.execute('PRAGMA busy_timeout=12000')
c.execute("""CREATE TABLE IF NOT EXISTS porfirchik_vk_history(
 peer_id INTEGER NOT NULL,
 message_id INTEGER NOT NULL,
 date INTEGER NOT NULL,
 from_id INTEGER NOT NULL,
 outgoing INTEGER NOT NULL,
 message_text TEXT NOT NULL,
 source_json TEXT NOT NULL,
 PRIMARY KEY(peer_id,message_id)
)""")
inserted=0
for m in rows:
 peer=int(m.get('peer_id') or 0);mid=int(m.get('id') or 0)
 if peer not in (452972559,691392544) or mid<1:continue
 text=str(m.get('text') or '')[:16000]
 raw=json.dumps(m,ensure_ascii=False,separators=(',',':'))
 if len(raw)>50000:raw=json.dumps({k:v for k,v in m.items() if k not in ('attachments','fwd_messages')},ensure_ascii=False)
 q=c.execute('INSERT OR IGNORE INTO porfirchik_vk_history(peer_id,message_id,date,from_id,outgoing,message_text,source_json) VALUES(?,?,?,?,?,?,?)',(peer,mid,int(m.get('date') or 0),int(m.get('from_id') or 0),int(m.get('out') or 0),text,raw))
 inserted+=int(q.rowcount or 0)
c.commit()
total=c.execute('SELECT COUNT(*) FROM porfirchik_vk_history').fetchone()[0]
c.close()
print(json.dumps({'ok':True,'inserted':inserted,'total':total}))`;
async function fetchPage(peer,offset){
 const b=new URLSearchParams({access_token:token,v:'5.199',peer_id:String(peer),count:'200',offset:String(offset)});
 const resp=await fetch('https://api.vk.com/method/messages.getHistory',{method:'POST',body:b,signal:AbortSignal.timeout(10000)});
 const d=await resp.json();
 if(!resp.ok||d.error||!d.response?.items)throw Error('vk_history_api_'+String(d.error?.error_code||resp.status));
 return d.response;
}
async function backfill(){
 if(!token||peers.some(p=>!allow.has(p))){console.log('ND_VK_BACKFILL_ABORT',JSON.stringify({reason:'token_or_allowlist_incomplete'}));return}
 const items=[],counts=[];
 try{
  for(const peer of peers){
   const first=await fetchPage(peer,0);
   const available=Math.min(Math.max(0,Number(first.count||0)),2400);
   const collected=[...first.items.filter(x=>Number(x.peer_id)===peer)];
   for(let offset=200;offset<available;offset+=200){
    await sleep(430);
    const page=await fetchPage(peer,offset);
    collected.push(...page.items.filter(x=>Number(x.peer_id)===peer));
    if(!page.items.length)throw Error('unexpected_empty_history_page');
   }
   if(collected.length<available)throw Error('vk_history_incomplete');
   items.push(...collected);
   counts.push({peer_id:peer,reported:Number(first.count||0),collected:collected.length});
   await sleep(430);
  }
  if(items.length<1)throw Error('no_history_records');
  const source='/tmp/nd-pfm-history-'+String(process.pid)+'.json';
  try{
   await fs.writeFile(source,JSON.stringify(items),{flag:'w',mode:0o600});
   const {stdout}=await execute('python3',['-c',python,db,source],{timeout:20000,maxBuffer:12000});
   const saved=JSON.parse(stdout.trim());
   if(!saved.ok||saved.total<items.length)throw Error('sqlite_history_write_short');
   console.log('ND_VK_BACKFILL_VERIFIED',JSON.stringify({api_counts:counts,archive_rows:saved.total,inserted:saved.inserted,table:'porfirchik_vk_history',normal_memory_untouched:true}));
  }finally{await fs.unlink(source).catch(()=>{})}
 }catch(e){console.log('ND_VK_BACKFILL_FAILED',JSON.stringify({type:e?.name||'Error',reason:String(e?.message||'').slice(0,90),api_counts:counts}))}
}
if(token) {
 setTimeout(()=>void backfill(),55000).unref();
 console.log('ND_VK_BACKFILL_SCHEDULED',JSON.stringify({peer_count:peers.length,max_messages_per_peer:2400,normal_memory_untouched:true}));
}
