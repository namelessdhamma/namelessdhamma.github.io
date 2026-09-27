const TOKEN=String(process.env.YANDEX_DISK_TOKEN||'').trim();
const rid='SvdxjDw6Up4iu6F455kJajo2OMyZqj1Bp706dh7JxJDbiORX_gs05UmEdqDk_TRqT4C9JOnX0Tx4ILycQU4gGwVezKs8FaXWg9Z5on_TZAMj3oJ6moc5u9rNKqCM_nCo';
const sk='55647bc32e518ea6b49db46e6e8a411067c089fd:1790524432';
const body={apiMethod:'mpfs/office-set-access-state',requestParams:{resourceId:rid,accessState:'all'},sk};
const resp=await fetch('https://disk.yandex.ru/models-v2?m=mpfs/office-set-access-state',{method:'POST',headers:{Authorization:'OAuth '+TOKEN,'Content-Type':'application/json','User-Agent':'Mozilla/5.0'},body:JSON.stringify(body)});
const txt=await resp.text();
console.log('PRIVATE_DIRECT_PROBE '+JSON.stringify({status:resp.status,ok:resp.ok,response:txt.slice(0,300).replace(/[A-Za-z0-9_-]{24,}/g,'[REDACTED]')}));
