import fs from 'node:fs';

const sourcePath='/app/server.mjs';
const runtimePath='/app/server.porfirchik-v20-7-7.mjs';
let s=fs.readFileSync(sourcePath,'utf8');

const replaceOne=(from,to,label)=>{
  const n=s.split(from).length-1;
  if(n!==1) throw new Error('Porfirchik V20.7.7 activation anchor mismatch: '+label+' count='+n);
  s=s.replace(from,to);
};

replaceOne(
  "const ND_PORFIRCHIK_GATEWAY_V20_7_4='porfirchik-v20.7.4-free-music-yandex-fallback-20260930';",
  "const ND_PORFIRCHIK_GATEWAY_V20_7_4='porfirchik-v20.7.7-free-music-yandex-signed-link-20260930';",
  'revision'
);
replaceOne(
  "const PORFIRCHIK_SOURCE_COMMIT='9b7da70f9e05188966d52c73f5b55d772267006a';",
  "const PORFIRCHIK_SOURCE_COMMIT='25917222d6e77f3c2e579ce8082378710a1487f3';",
  'source_commit'
);
replaceOne(
  "const PORFIRCHIK_SOURCE_PATH='tmp/nd_vk_v20_7_4_music_yandex_fallback_loader.py';",
  "const PORFIRCHIK_SOURCE_PATH='tmp/nd_vk_v20_7_7_music_yandex_signed_link_loader.py';",
  'source_path'
);

const routeAnchor="    if(path==='/porfirchik/health'){";
const routeBlock=`    if(path.startsWith('/porfirchik/music/')){
      if(req.method!=='GET'){res.writeHead(405,{Allow:'GET','content-length':'0'});res.end();return;}
      try{
        const parts=path.split('/').filter(Boolean);
        if(parts.length!==4||parts[0]!=='porfirchik'||parts[1]!=='music')throw new Error('invalid_music_link');
        const sig=String(parts[2]||''), encoded=String(parts[3]||'');
        const expected=createHash('sha256').update('music-link:'+PORFIRCHIK_VK_TOKEN+':'+encoded).digest('hex').slice(0,32);
        if(!PORFIRCHIK_VK_TOKEN||sig!==expected)throw new Error('invalid_music_signature');
        const pad='='.repeat((4-(encoded.length%4))%4);
        const diskPath=Buffer.from((encoded+pad).replace(/-/g,'+').replace(/_/g,'/'),'base64').toString('utf8');
        if(!diskPath.startsWith('disk:/Porfirchik Music/'))throw new Error('invalid_music_path');
        const d=await api('/resources/download',{path:diskPath});
        const href=String(d?.href||'');
        if(!href.startsWith('https://'))throw new Error('music_download_href_missing');
        res.writeHead(302,{location:href,'cache-control':'no-store','content-length':'0'});
        res.end();return;
      }catch{
        return j(res,404,{ok:false,error:'music_link_unavailable'});
      }
    }

    if(path==='/porfirchik/health'){`;
replaceOne(routeAnchor,routeBlock,'music_route');

fs.writeFileSync(runtimePath,s);
console.log('ND_PORFIRCHIK_V20_7_7_ACTIVATION_SHIM_READY');
await import('file://'+runtimePath);
