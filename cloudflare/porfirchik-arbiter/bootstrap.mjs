import http from 'node:http';
import { spawn } from 'node:child_process';

const PORT=Number(process.env.PORT||3000);
const RENDER_SERVICE_ID='srv-daveornavr4c73bno810';
const RENDER_API='https://api.render.com/v1';
const state={ok:false,stage:'starting',worker_url:null,render_synced:false,worker_deployed:false,secret_set:false,error:null,started_at:new Date().toISOString(),finished_at:null};

function clean(e){let s=String(e&&e.message||e||'error');for(const k of ['CLOUDFLARE_API_TOKEN','RENDER_API_TOKEN','VK_GROUP_TOKEN']){const v=process.env[k];if(v)s=s.split(v).join('[redacted]')}return s.slice(0,1200)}
function run(cmd,args,input=''){return new Promise((resolve,reject)=>{const p=spawn(cmd,args,{env:process.env,stdio:['pipe','pipe','pipe']});let out='',err='';p.stdout.on('data',d=>out+=d);p.stderr.on('data',d=>err+=d);p.on('error',reject);p.on('close',code=>code===0?resolve({out,err}):reject(new Error(cmd+' '+args.join(' ')+' exit '+code+': '+(err||out).slice(-1800))));if(input)p.stdin.end(input);else p.stdin.end();});}
async function renderSet(key,value){
  const r=await fetch(RENDER_API+'/services/'+RENDER_SERVICE_ID+'/env-vars/'+encodeURIComponent(key),{
    method:'PUT',
    headers:{Authorization:'Bearer '+process.env.RENDER_API_TOKEN,'Content-Type':'application/json','Accept':'application/json'},
    body:JSON.stringify({value:String(value??'')})
  });
  if(!r.ok)throw new Error('Render env '+key+' HTTP '+r.status+': '+(await r.text()).slice(0,500));
}
function requireEnv(k){const v=String(process.env[k]||'');if(!v)throw new Error(k+' missing');return v;}
async function main(){
  try{
    requireEnv('CLOUDFLARE_API_TOKEN');requireEnv('CLOUDFLARE_ACCOUNT_ID');requireEnv('RENDER_API_TOKEN');requireEnv('VK_GROUP_TOKEN');
    state.stage='render_env';
    const map={
      VK_GROUP_TOKEN:process.env.VK_GROUP_TOKEN,
      VK_ALLOWED_USER_IDS:process.env.VK_ALLOWED_USER_IDS,
      VK_API_VERSION:process.env.VK_API_VERSION||'5.199',
      VK_GROUP_SCREEN_NAME:process.env.VK_GROUP_SCREEN_NAME||'namelessdhamma',
      GROQ_API_KEY:process.env.GROQ_API_KEY,
      GROQ_MODEL:process.env.GROQ_MODEL,
      GROQ_RESEARCH_MODEL:process.env.GROQ_RESEARCH_MODEL,
      OpenRouter:process.env.OpenRouter,
      OPENROUTER_API_KEY:process.env.OpenRouter,
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
      PORFIRCHIK_MEMOS_BOT_TOKEN:process.env.PORFIRCHIK_MEMOS_BOT_TOKEN,
      PORFIRCHIK_MEMOS_ADMIN_ROUTE:process.env.PORFIRCHIK_MEMOS_ADMIN_ROUTE,
      YANDEX_DISK_TOKEN:process.env.YANDEX_DISK_TOKEN,
      HF_TOKEN:process.env.HF_TOKEN,
      PORFIRCHIK_MUSIC_SPACE_BASE:process.env.PORFIRCHIK_MUSIC_SPACE_BASE,
      PORFIRCHIK_ARB_MODE:'managed',
      PORFIRCHIK_ARB_OWNER:'RENDER',
      PORFIRCHIK_MEMOS_LOCAL_DB:'/tmp/porfirchik-memos.sqlite3'
    };
    for(const [k,v] of Object.entries(map))if(v!==undefined&&v!==null&&String(v)!=='')await renderSet(k,v);
    state.render_synced=true;

    state.stage='worker_deploy';
    const dep=await run('npx',['wrangler','deploy','--config','wrangler.jsonc']);
    const all=(dep.out+'\n'+dep.err);
    const m=all.match(/https:\/\/[A-Za-z0-9._-]+\.workers\.dev/);
    if(!m)throw new Error('workers.dev URL not found in deploy output');
    state.worker_url=m[0].replace(/\/+$/,'');
    state.worker_deployed=true;

    state.stage='worker_secret';
    await run('npx',['wrangler','secret','put','VK_GROUP_TOKEN','--name','nd-porfirchik-arbiter'],process.env.VK_GROUP_TOKEN+'\n');
    state.secret_set=true;

    state.stage='render_arbiter_url';
    await renderSet('PORFIRCHIK_ARB_BASE_URL',state.worker_url);
    state.ok=true;state.stage='done';state.finished_at=new Date().toISOString();
    console.log('PORFIRCHIK_FAILOVER_BOOTSTRAP_DONE',JSON.stringify({worker_url:state.worker_url,render_synced:true,worker_deployed:true,secret_set:true}));
  }catch(e){state.error=clean(e);state.stage='error';state.finished_at=new Date().toISOString();console.error('PORFIRCHIK_FAILOVER_BOOTSTRAP_ERROR',state.error)}
}
http.createServer((req,res)=>{const body=Buffer.from(JSON.stringify(state));res.writeHead(state.ok?200:state.stage==='error'?500:202,{'content-type':'application/json','cache-control':'no-store','content-length':String(body.length)});res.end(body)}).listen(PORT,'0.0.0.0',()=>{console.log('PORFIRCHIK_FAILOVER_BOOTSTRAP_READY');main()});
