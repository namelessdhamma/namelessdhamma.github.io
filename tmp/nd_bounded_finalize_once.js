const http=require('http'),crypto=require('crypto'),zlib=require('zlib');
const PORT=Number(process.env.PORT||3000), S={done:false,drive:{},yandex:{}};
const e=n=>(process.env[n]||'').trim();
const bu=x=>Buffer.from(x).toString('base64').replace(/=/g,'').replace(/\+/g,'-').replace(/\//g,'_');
async function gt(){
 const email=e('ND_GOOGLE_CLIENT_EMAIL'),raw=e('ND_GOOGLE_PRIVATE_KEY_B64'); if(!email||!raw)throw Error('google_credentials_missing');
 let key=Buffer.from(raw,'base64').toString('utf8'); try{if(!key.includes('BEGIN PRIVATE KEY'))key=JSON.parse(key).private_key||key}catch{} key=key.replace(/\\n/g,'\n');
 const now=Math.floor(Date.now()/1000),h=bu(JSON.stringify({alg:'RS256',typ:'JWT'})),p=bu(JSON.stringify({iss:email,scope:'https://www.googleapis.com/auth/drive',aud:'https://oauth2.googleapis.com/token',iat:now,exp:now+3600})),i=h+'.'+p;
 const sig=crypto.createSign('RSA-SHA256').update(i).end().sign(key),a=i+'.'+bu(sig),b=new URLSearchParams({grant_type:'urn:ietf:params:oauth-type:jwt-bearer',assertion:a});
 b.set('grant_type','urn:ietf:params:oauth:grant-type:jwt-bearer');
 const r=await fetch('https://oauth2.googleapis.com/token',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:b}); if(!r.ok)throw Error('google_token_'+r.status); const j=await r.json(); return j.access_token;
}
async function drive(){
 try{
  const id=e('ND_FINALIZE_DRIVE_FILE_ID'),rev=e('ND_FINALIZE_DRIVE_REV_ID'),want=Number(e('ND_FINALIZE_DRIVE_SIZE')); if(!id||!rev||!want)throw Error('drive_inputs_missing');
  const t=await gt(),rr=await fetch('https://www.googleapis.com/drive/v3/files/'+encodeURIComponent(id)+'/revisions/'+encodeURIComponent(rev)+'?alt=media&supportsAllDrives=true',{headers:{Authorization:'Bearer '+t}}); if(!rr.ok)throw Error('revision_read_'+rr.status);
  const buf=Buffer.from(await rr.arrayBuffer()); S.drive.read=buf.length; if(buf.length!==want)throw Error('revision_size_'+buf.length);
  const ur=await fetch('https://www.googleapis.com/upload/drive/v3/files/'+encodeURIComponent(id)+'?uploadType=media&supportsAllDrives=true',{method:'PATCH',headers:{Authorization:'Bearer '+t,'Content-Type':'application/octet-stream','Content-Length':String(buf.length)},body:buf}); if(!ur.ok)throw Error('drive_upload_'+ur.status);
  const vr=await fetch('https://www.googleapis.com/drive/v3/files/'+encodeURIComponent(id)+'?fields=size&supportsAllDrives=true',{headers:{Authorization:'Bearer '+t}}),v=await vr.json(); S.drive.size=Number(v.size||0); S.drive.ok=S.drive.size===want;
 }catch(x){S.drive.ok=false;S.drive.error=String(x.message||x).slice(0,200)}
}
async function yandex(){
 try{
  const token=e('YANDEX_DISK_TOKEN'),path=e('ND_FINALIZE_YANDEX_PATH'),gz=e('ND_FINALIZE_TEXT_GZ'); if(!token||!path||!gz)throw Error('yandex_inputs_missing');
  const body=zlib.gunzipSync(Buffer.from(gz,'base64')),sha=crypto.createHash('sha256').update(body).digest('hex'),md5=crypto.createHash('md5').update(body).digest('hex');
  let q=new URLSearchParams({path,overwrite:'true'}),r=await fetch('https://cloud-api.yandex.net/v1/disk/resources/upload?'+q,{headers:{Authorization:'OAuth '+token}}); if(!r.ok)throw Error('yandex_url_'+r.status); let j=await r.json();
  r=await fetch(j.href,{method:'PUT',headers:{'Content-Type':'text/plain; charset=utf-8','Content-Length':String(body.length)},body}); if(!r.ok)throw Error('yandex_put_'+r.status);
  await new Promise(a=>setTimeout(a,1000)); q=new URLSearchParams({path,fields:'size,md5,sha256'}); r=await fetch('https://cloud-api.yandex.net/v1/disk/resources?'+q,{headers:{Authorization:'OAuth '+token}}); if(!r.ok)throw Error('yandex_meta_'+r.status); j=await r.json();
  S.yandex.size=Number(j.size||0); S.yandex.ok=S.yandex.size===body.length&&(!j.sha256||j.sha256===sha)&&(!j.md5||j.md5===md5);
 }catch(x){S.yandex.ok=false;S.yandex.error=String(x.message||x).slice(0,200)}
}
http.createServer((q,r)=>{r.writeHead(200,{'Content-Type':'application/json'});r.end(JSON.stringify({ok:true,done:S.done,drive_ok:!!S.drive.ok,yandex_ok:!!S.yandex.ok}))}).listen(PORT,'0.0.0.0');
(async()=>{await drive();await yandex();S.done=true;console.log('ND_FINALIZE_RESULT '+JSON.stringify(S))})().catch(x=>{S.done=true;console.log('ND_FINALIZE_FATAL '+String(x.message||x).slice(0,200))});
