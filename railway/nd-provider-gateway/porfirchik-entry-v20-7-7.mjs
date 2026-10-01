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
  "const ND_PORFIRCHIK_GATEWAY_V20_7_4='porfirchik-v20.7.15-music-links-proxy-20261002';",
  'revision'
);
replaceOne(
  "const PORFIRCHIK_SOURCE_COMMIT='9b7da70f9e05188966d52c73f5b55d772267006a';",
  "const PORFIRCHIK_SOURCE_COMMIT='26c49263363414c4b1e26b21eadbd105bb9b4859';",
  'source_commit'
);
replaceOne(
  "const PORFIRCHIK_SOURCE_PATH='tmp/nd_vk_v20_7_4_music_yandex_fallback_loader.py';",
  "const PORFIRCHIK_SOURCE_PATH='tmp/nd_vk_v20_7_14_quarantine_legacy_probes_loader.py';",
  'source_path'
);

replaceOne(
  "for(const key of ['CEREBRAS_API_KEY','MISTRAL_API_KEY','OPENAI_API_KEY','ZAI_API_KEY','OMNIROUTE_BASE_URL']){",
  "for(const key of ['OPENAI_API_KEY','OMNIROUTE_BASE_URL']){",
  'restore_historical_free_provider_env'
);

const routeAnchor="    if(path==='/porfirchik/health'){";
const routeBlock="    if(path.startsWith('/porfirchik/music/')){\n      if(req.method!=='GET'&&req.method!=='HEAD'){\n        res.writeHead(405,{Allow:'GET, HEAD','content-length':'0'});res.end();return;\n      }\n      const parts=path.split('/').filter(Boolean);\n      const sig=String(parts[2]||''),encoded=String(parts[3]||'');\n      if(parts.length!==4||parts[0]!=='porfirchik'||parts[1]!=='music'||\n         !/^[a-f0-9]{32}$/.test(sig)||!/^[A-Za-z0-9_-]{12,512}$/.test(encoded)||\n         !PORFIRCHIK_VK_TOKEN){\n        return j(res,404,{ok:false,error:'invalid_music_link'});\n      }\n      const expected=createHash('sha256').update('music-link:'+PORFIRCHIK_VK_TOKEN+':'+encoded).digest('hex').slice(0,32);\n      if(sig!==expected){\n        return j(res,404,{ok:false,error:'invalid_music_link'});\n      }\n      const pad='='.repeat((4-(encoded.length%4))%4);\n      const diskPath=Buffer.from((encoded+pad).replace(/-/g,'+').replace(/_/g,'/'),'base64').toString('utf8');\n      const filename=diskPath.split('/').pop()||'porfirchik-music.wav';\n      if(!diskPath.startsWith('disk:/Porfirchik Music/')||!/^[A-Za-z0-9_.-]+[.]wav$/i.test(filename)){\n        return j(res,404,{ok:false,error:'invalid_music_resource'});\n      }\n      try{\n        const meta=await api('/resources',{path:diskPath,fields:'name,size,mime_type'});\n        const declaredSize=Number(meta?.size||0);\n        if(!declaredSize||declaredSize>35000000){\n          return j(res,422,{ok:false,error:'invalid_music_file_size'});\n        }\n        const raw=requestUrl.searchParams.get('raw')==='1';\n        const download=requestUrl.searchParams.get('download')==='1';\n        if(!raw&&!download){\n          const mb=(declaredSize/1048576).toFixed(1);\n          const html=[\n            '<!doctype html><html lang=\"ru\"><head><meta charset=\"utf-8\">',\n            '<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">',\n            '<title>Музыка Порфирчика</title>',\n            '<style>body{font-family:system-ui,-apple-system,sans-serif;margin:0;padding:24px;background:#f8fafc;color:#17212b}',\n            'main{max-width:560px;margin:7vh auto;padding:24px;border-radius:18px;background:white;box-shadow:0 6px 28px #0001}',\n            'audio{width:100%;margin:16px 0}a{display:inline-block;padding:12px 18px;background:#2776d2;color:white;border-radius:9px;text-decoration:none}',\n            'p{line-height:1.5}small{color:#667085}</style></head><body><main>',\n            '<h1>Музыка готова</h1><p>Нажмите «Воспроизвести» или скачайте WAV на устройство.</p>',\n            '<audio controls preload=\"metadata\" src=\"'+path+'?raw=1\"></audio>',\n            '<p><a href=\"'+path+'?download=1\">Скачать WAV</a></p>',\n            '<small>WAV · '+mb+' МБ · файл сохранён на Яндекс.Диске</small>',\n            '</main></body></html>'\n          ].join('');\n          const bytes=Buffer.from(html,'utf8');\n          res.writeHead(200,{'content-type':'text/html; charset=utf-8',\n            'content-length':String(bytes.length),'cache-control':'no-store',\n            'x-content-type-options':'nosniff',\n            'content-security-policy':\"default-src 'none'; media-src 'self'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\"});\n          if(req.method==='HEAD'){res.end();return;}\n          res.end(bytes);return;\n        }\n        const link=await api('/resources/download',{path:diskPath});\n        const href=String(link?.href||'');\n        if(!href.startsWith('https://')){\n          return j(res,502,{ok:false,error:'music_download_unavailable'});\n        }\n        const range=String(req.headers.range||'');\n        if(range&&!/^bytes=\\d*-\\d*$/.test(range)){\n          return j(res,416,{ok:false,error:'invalid_range'});\n        }\n        const opts={method:'GET',redirect:'follow',\n          headers:range?{Range:range}:{},\n          signal:AbortSignal.timeout(150000)};\n        const upstream=await boundedFetch(href,opts,30000);\n        if(!(upstream.status===200||upstream.status===206)){\n          console.log('PORFIRCHIK_MUSIC_UPSTREAM_ERROR',JSON.stringify({status:upstream.status}));\n          return j(res,502,{ok:false,error:'music_file_temporarily_unavailable'});\n        }\n        const length=Number(upstream.headers.get('content-length')||0);\n        if(length>35000000){\n          return j(res,413,{ok:false,error:'music_file_too_large'});\n        }\n        const bytes=Buffer.from(await upstream.arrayBuffer());\n        if(!bytes.length||bytes.length>35000000){\n          return j(res,502,{ok:false,error:'music_file_invalid'});\n        }\n        if((!range||/^bytes=0-/.test(range))&&\n           (bytes.length<12||bytes.toString('ascii',0,4)!=='RIFF'||bytes.toString('ascii',8,12)!=='WAVE')){\n          console.log('PORFIRCHIK_MUSIC_INVALID_WAV',JSON.stringify({bytes:bytes.length,status:upstream.status}));\n          return j(res,502,{ok:false,error:'music_audio_unavailable'});\n        }\n        const code=upstream.status===206?206:200;\n        const headers={'content-type':'audio/wav','content-length':String(bytes.length),\n          'content-disposition':(download?'attachment':'inline')+'; filename=\"'+filename+'\"',\n          'cache-control':'private, no-store','x-content-type-options':'nosniff',\n          'accept-ranges':'bytes'};\n        if(code===206&&upstream.headers.get('content-range')){\n          headers['content-range']=upstream.headers.get('content-range');\n        }\n        console.log('PORFIRCHIK_MUSIC_PROXY_OK',JSON.stringify({status:code,bytes:bytes.length,download,partial:code===206}));\n        res.writeHead(code,headers);\n        if(req.method==='HEAD'){res.end();return;}\n        res.end(bytes);return;\n      }catch(err){\n        console.log('PORFIRCHIK_MUSIC_PROXY_ERROR',JSON.stringify({stage:'yandex_fetch',type:String(err?.name||'error').slice(0,35)}));\n        return j(res,502,{ok:false,error:'music_file_temporarily_unavailable'});\n      }\n    }\n\n    ";
replaceOne(routeAnchor,routeBlock,'music_route');

fs.writeFileSync(runtimePath,s);
console.log('ND_PORFIRCHIK_V20_7_7_ACTIVATION_SHIM_READY');
await import('file://'+runtimePath);
