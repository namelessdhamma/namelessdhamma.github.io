import crypto from 'node:crypto';
const keys=['ND_YANDEX_SHARE_TEST_JS','ND_SHARE_BATCH_JS','ND_EDITLINK_TEST','ND_YANDEX_VERIFY_JS','ND_YANDEX_AUDIT_JS','ND_YANDEX_AUDIT_JS_B64','ND_YANDEX_GATEWAY_B64'];
const out={};
for (const k of keys){
  const s=String(process.env[k]||'');
  const paths=[...s.matchAll(/disk:\/[^"'\`\s]+(?:\s[^"'\`\n\r]*)?/g)].slice(0,12).map(m=>m[0].slice(0,220));
  const urls=[...s.matchAll(/https?:\/\/[^"'\`\s)]+/g)].slice(0,12).map(m=>{try{return new URL(m[0]).host+new URL(m[0]).pathname}catch{return 'invalid'}});
  out[k]={
    present:!!s,
    length:s.length,
    sha256:s?crypto.createHash('sha256').update(s).digest('hex'):null,
    flags:{
      models_v2:s.includes('models-v2'),
      office_set:s.includes('office-set-access-state'),
      get_public:s.includes('get-public-settings'),
      accessState:s.includes('accessState'),
      connection_id:s.includes('connection_id'),
      resourceId:s.includes('resourceId'),
      cookie:/cookie/i.test(s),
      cloud_api:s.includes('cloud-api.yandex.net'),
      son:/сон том 2/i.test(s),
      blue:/Синее море/i.test(s)
    },
    paths,urls
  };
}
console.log('ND_YANDEX_SCRIPT_INSPECT '+JSON.stringify(out));
