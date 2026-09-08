const H={Authorization:'OAuth '+process.env.YANDEX_DISK_TOKEN},A='https://cloud-api.yandex.net/v1/disk';
const b=Buffer.from((await (await fetch('https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/main/tmp/story0_20260908.b64')).text()).trim(),'base64');
const n='000_Краткое эссе о недоступном знании и искусстве внимательности.docx';
async function j(u,o={}){let r=await fetch(u,{...o,headers:{...H,...(o.headers||{})}});let t=await r.text();if(!r.ok)throw Error(r.status+' '+t);return t?JSON.parse(t):{}}
async function up(p){let u=new URL(A+'/resources/upload');u.searchParams.set('path',p);u.searchParams.set('overwrite','true');let x=await j(u);let r=await fetch(x.href,{method:'PUT',body:b});if(!r.ok)throw Error('upload '+r.status);let q=new URL(A+'/resources/publish');q.searchParams.set('path',p);r=await fetch(q,{method:'PUT',headers:H});if(!r.ok&&r.status!==409)throw Error('publish '+r.status);let m=new URL(A+'/resources');m.searchParams.set('path',p);return await j(m)}
let ps=['disk:/сон том 2/Проработка глав/'+n,'disk:/сон том 2/Черновики/'+n],z=[];for(let p of ps)z.push(await up(p));
console.log('NDZERO '+JSON.stringify(z.map(x=>({path:x.path,size:x.size,public_url:x.public_url,md5:x.md5}))));
