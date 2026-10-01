import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';

await import('./porfirchik-entry-v20-7-7.mjs');

const ENABLED=String(process.env.PORFIRCHIK_FAILOVER_BOOTSTRAP||'').trim()==='1';
const MARKER='/memos-data/porfirchik-failover-bootstrap-v1.json';
const RENDER_SERVICE_ID='srv-daveornavr4c73bno810';
const RENDER_API='https://api.render.com/v1';
const WORKER_COMMIT='5522430b741d662d24ae2700ca79a4c2df9829ee';
const RAW='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/'+WORKER_COMMIT+'/cloudflare/porfirchik-arbiter/worker.mjs';
const DIR='/tmp/nd-porfirchik-arbiter-bootstrap';

function clean(e){
  let s=String(e?.message||e||'error');
  for(const k of ['CLOUDFLARE_API_TOKEN','ND_NOTEBOOKLM_BOOTSTRAP_RENDER_TOKEN','VK_GROUP_TOKEN']){
    const v=process.env[k]; if(v)s=s.split(v).join('[redacted]');
  }
  return s.slice(0,1600);
}
function run(cmd,args,cwd,input=''){
  return new Promise((resolve,reject)=>{
    const p=spawn(cmd,args,{cwd,env:process.env,stdio:['pipe','pipe','pipe']});
    let out='',err='';
    p.stdout.on('data',d=>out+=String(d));
    p.stderr.on('data',d=>err+=String(d));
    p.on('error',reject);
    p.on('close',code=>code===0?resolve({out,err}):reject(new Error(cmd+' exit '+code+': '+(err||out).slice(-1800))));
    p.stdin.end(input);
  });
}
async function renderSet(key,value){
  if(value===undefined||value===null||String(value)==='')return;
  const tok=String(process.env.ND_NOTEBOOKLM_BOOTSTRAP_RENDER_TOKEN||'');
  if(!tok)throw new Error('Render bootstrap token missing');
  const r=await fetch(RENDER_API+'/services/'+RENDER_SERVICE_ID+'/env-vars/'+encodeURIComponent(key),{
    method:'PUT',
    headers:{Authorization:'Bearer '+tok,'Content-Type':'application/json','Accept':'application/json'},
    body:JSON.stringify({value:String(value)})
  });
  if(!r.ok)throw new Error('Render env '+key+' HTTP '+r.status+': '+(await r.text()).slice(0,400));
}
async function bootstrap(){
  if(!ENABLED)return;
  try{
    if(fs.existsSync(MARKER)){
      const old=JSON.parse(fs.readFileSync(MARKER,'utf8'));
      if(old?.ok&&old?.worker_url){console.log('PORFIRCHIK_FAILOVER_BOOTSTRAP_ALREADY_DONE',JSON.stringify({worker_url:old.worker_url}));return;}
    }
    for(const k of ['CLOUDFLARE_ACCOUNT_ID','CLOUDFLARE_API_TOKEN','VK_GROUP_TOKEN','ND_NOTEBOOKLM_BOOTSTRAP_RENDER_TOKEN']){
      if(!String(process.env[k]||''))throw new Error(k+' missing');
    }

    fs.mkdirSync(DIR,{recursive:true});
    const wr=await fetch(RAW,{signal:AbortSignal.timeout(30000)});
    if(!wr.ok)throw new Error('worker fetch HTTP '+wr.status);
    fs.writeFileSync(path.join(DIR,'worker.mjs'),await wr.text());
    const cfg={
      $schema:'https://raw.githubusercontent.com/cloudflare/workers-sdk/main/packages/wrangler/config-schema.json',
      name:'nd-porfirchik-arbiter',
      main:'worker.mjs',
      compatibility_date:'2026-10-02',
      workers_dev:true,
      durable_objects:{bindings:[{name:'ARBITER',class_name:'PorfirchikArbiter'}]},
      migrations:[{tag:'v1',new_sqlite_classes:['PorfirchikArbiter']}],
      vars:{
        RAILWAY_BASE_URL:'https://nd-yandex-n8n-gateway-production.up.railway.app',
        RENDER_BASE_URL:'https://nd-porfirchik-cold.onrender.com',
        VK_API_VERSION:String(process.env.VK_API_VERSION||'5.199'),
        QUALIFICATION_MODE:'1'
      }
    };
    fs.writeFileSync(path.join(DIR,'wrangler.json'),JSON.stringify(cfg));

    const map={
      VK_GROUP_TOKEN:process.env.VK_GROUP_TOKEN,
      VK_ALLOWED_USER_IDS:process.env.VK_ALLOWED_USER_IDS,
      VK_API_VERSION:process.env.VK_API_VERSION||'5.199',
      VK_GROUP_SCREEN_NAME:process.env.VK_GROUP_SCREEN_NAME||'namelessdhamma',
      GROQ_API_KEY:process.env.GROQ_API_KEY,
      GROQ_MODEL:process.env.GROQ_MODEL,
      GROQ_RESEARCH_MODEL:process.env.GROQ_RESEARCH_MODEL,
      OpenRouter:process.env.OpenRouter,
      OPENROUTER_API_KEY:process.env.OpenRouter||process.env.OPENROUTER_API_KEY,
      OPENROUTER_MODEL:process.env.OPENROUTER_MODEL,
      CLOUDFLARE_ACCOUNT_ID:process.env.CLOUDFLARE_ACCOUNT_ID,
      CLOUDFLARE_API_TOKEN:process.env.CLOUDFLARE_API_TOKEN,
      CLOUDFLARE_MODEL:process.env.CLOUDFLARE_MODEL,
      ZAI_API_KEY:process.env.ZAI_API_KEY,
      ZAI_MODEL:process.env.ZAI_MODEL,
      CEREBRAS_API_KEY:process.env.CEREBRAS_API_KEY,
      CEREBRAS_MODEL:process.env.CEREBRAS_MODEL,
      MISTRAL_API_KEY:process.env.MISTRAL_API_KEY,
      MISTRAL_MODEL:process.env.MISTRAL_MODEL,
      MEMOS_API_KEY:process.env.MEMOS_API_KEY,
      MEMOS_CLOUD_URL:process.env.MEMOS_CLOUD_URL,
      MEMOS_APP_ID:process.env.MEMOS_APP_ID,
      MEMOS_AGENT_ID:process.env.MEMOS_AGENT_ID,
      MEMOS_USER_ID:process.env.MEMOS_USER_ID,
      MEMOS_USER_PREFIX:process.env.MEMOS_USER_PREFIX,
      MEMOS_USER_SALT:process.env.MEMOS_USER_SALT,
      MEMOS_HOME:process.env.MEMOS_HOME,
      ND_MEMOS_REV:process.env.ND_MEMOS_REV,
      PORFIRCHIK_MEMOS_BOT_TOKEN:process.env.PORFIRCHIK_MEMOS_BOT_TOKEN,
      PORFIRCHIK_MEMOS_ADMIN_ROUTE:process.env.PORFIRCHIK_MEMOS_ADMIN_ROUTE,
      YANDEX_DISK_TOKEN:process.env.YANDEX_DISK_TOKEN,
      HF_TOKEN:process.env.HF_TOKEN,
      PORFIRCHIK_MUSIC_SPACE_BASE:process.env.PORFIRCHIK_MUSIC_SPACE_BASE,
      PORFIRCHIK_ARB_MODE:'managed',
      PORFIRCHIK_ARB_OWNER:'RENDER',
      PORFIRCHIK_MEMOS_LOCAL_DB:'/tmp/porfirchik-memos.sqlite3'
    };
    for(const [k,v] of Object.entries(map))await renderSet(k,v);
    console.log('PORFIRCHIK_FAILOVER_RENDER_ENV_SYNCED',JSON.stringify({keys:Object.entries(map).filter(([,v])=>v!==undefined&&v!==null&&String(v)!=='').length}));

    const dep=await run('npx',['-y','wrangler@4.42.0','deploy','--config','wrangler.json'],DIR);
    const output=dep.out+'\n'+dep.err;
    const m=output.match(/https:\/\/[A-Za-z0-9._-]+\.workers\.dev/);
    if(!m)throw new Error('workers.dev URL not found after deploy');
    const workerUrl=m[0].replace(/\/+$/,'');
    await run('npx',['-y','wrangler@4.42.0','secret','put','VK_GROUP_TOKEN','--name','nd-porfirchik-arbiter','--config','wrangler.json'],DIR,String(process.env.VK_GROUP_TOKEN)+'\n');
    await renderSet('PORFIRCHIK_ARB_BASE_URL',workerUrl);
    const done={ok:true,worker_url:workerUrl,render_service:RENDER_SERVICE_ID,worker_commit:WORKER_COMMIT,at:new Date().toISOString()};
    fs.writeFileSync(MARKER+'.tmp',JSON.stringify(done));
    fs.renameSync(MARKER+'.tmp',MARKER);
    console.log('PORFIRCHIK_FAILOVER_BOOTSTRAP_DONE',JSON.stringify(done));
  }catch(e){
    console.error('PORFIRCHIK_FAILOVER_BOOTSTRAP_ERROR',clean(e));
  }
}
setTimeout(()=>bootstrap(),2500).unref();
