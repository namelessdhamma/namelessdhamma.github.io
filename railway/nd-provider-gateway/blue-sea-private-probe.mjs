const API='https://cloud-api.yandex.net/v1/disk';
const TOKEN=String(process.env.YANDEX_DISK_TOKEN||'').trim();
const path='disk:/Синее море/Сценарий черновики/001_Эпизод 1_черновик.docx';
const headers={Authorization:'OAuth '+TOKEN,Accept:'application/json','Content-Type':'application/json'};
const u=new URL(API+'/public/resources/public-settings');
u.searchParams.set('path',path);u.searchParams.set('allow_address_access','true');
const payload={accesses:[{type:'macro',macros:['all'],rights:['write']}]};
const p=await fetch(u,{method:'PATCH',headers,body:JSON.stringify(payload)});
const pt=await p.text();let pd={};try{pd=JSON.parse(pt)}catch{pd={text:pt.slice(0,300)}}
const g=await fetch(u,{headers:{Authorization:'OAuth '+TOKEN,Accept:'application/json'}});
const gt=await g.text();let gd={};try{gd=JSON.parse(gt)}catch{gd={text:gt.slice(0,300)}}
console.log('ACL_PATCH_PROBE '+JSON.stringify({patch:{status:p.status,ok:p.ok,data:pd},readback:{status:g.status,ok:g.ok,data:gd}}));
