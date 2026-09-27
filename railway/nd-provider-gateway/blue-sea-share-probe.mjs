const API='https://cloud-api.yandex.net/v1/disk';
const TOKEN=String(process.env.YANDEX_DISK_TOKEN||'').trim();
if(!TOKEN) throw new Error('YANDEX_DISK_TOKEN missing');
const path='disk:/Синее море/Сценарий черновики/001_Эпизод 1_черновик.docx';
const u=new URL(API+'/public/resources/public-settings');
u.searchParams.set('path',path);
u.searchParams.set('allow_address_access','true');
const r=await fetch(u,{headers:{Authorization:'OAuth '+TOKEN,Accept:'application/json','User-Agent':'nd-yandex-blue-sea-share-probe/1.0'}});
const t=await r.text();
let d; try{d=JSON.parse(t)}catch{d={text:t.slice(0,1200)}}
console.log('BLUE_SEA_SHARE_PROBE',JSON.stringify({status:r.status,ok:r.ok,data:d}));
