const API='https://cloud-api.yandex.net/v1/disk';
const TOKEN=String(process.env.YANDEX_DISK_TOKEN||'').trim();
const path='disk:/Синее море/Сценарий черновики/001_Эпизод 1_черновик.docx';
async function jget(url,opts={}){const r=await fetch(url,opts);const t=await r.text();return {r,t};}
const u=new URL(API+'/resources');u.searchParams.set('path',path);u.searchParams.set('fields','public_url');
const meta=await (await fetch(u,{headers:{Authorization:'OAuth '+TOKEN,Accept:'application/json'}})).json();
const pg=await fetch(meta.public_url,{redirect:'follow',headers:{'User-Agent':'Mozilla/5.0'}});
const html=await pg.text();
const sk=(html.match(/"sk":"([^"]+)"/)||[])[1]||null;
const rid=(html.match(/\\?"resource_id\\?":\\?"([^"\\]+)\\?"/)||[])[1]||null;
if(!sk||!rid){console.log('PRIVATE_PROBE '+JSON.stringify({stage:'parse',status:pg.status,finalUrl:pg.url,sk:!!sk,rid:!!rid}));process.exit(0);}
const body={apiMethod:'mpfs/office-set-access-state',requestParams:{resourceId:rid,accessState:'all'},sk};
const resp=await fetch('https://disk.yandex.ru/models-v2?m=mpfs/office-set-access-state',{method:'POST',headers:{Authorization:'OAuth '+TOKEN,'Content-Type':'application/json','User-Agent':'Mozilla/5.0'},body:JSON.stringify(body)});
const txt=await resp.text();
console.log('PRIVATE_PROBE '+JSON.stringify({stage:'post',status:resp.status,ok:resp.ok,response:txt.slice(0,300).replace(/[A-Za-z0-9_-]{24,}/g,'[REDACTED]')}));
