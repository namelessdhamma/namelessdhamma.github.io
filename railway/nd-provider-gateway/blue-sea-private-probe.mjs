const token=String(process.env.YANDEX_DISK_TOKEN||'').trim();
const body=new URLSearchParams({type:'x-token',retpath:'https://www.yandex.ru'});
const r=await fetch('https://mobileproxy.passport.yandex.net/1/bundle/auth/x_token/',{
  method:'POST',
  headers:{'Content-Type':'application/x-www-form-urlencoded','Ya-Consumer-Authorization':'OAuth '+token,'User-Agent':'Mozilla/5.0'},
  body
});
const t=await r.text();let j={};try{j=JSON.parse(t)}catch{j={text:t.slice(0,200)}}
const safe={http:r.status,status:j.status||null,error:j.error||null,errors:j.errors||null,has_track:!!j.track_id,has_host:!!j.passport_host};
console.log('XTOKEN_PROBE '+JSON.stringify(safe));
