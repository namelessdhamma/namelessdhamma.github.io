// Porfirchik V21: the parent gateway (server.mjs) starts porfirchik.py from this folder
// instead of fetching loaders from GitHub. Render start command: node porfirchik-entry-v21.mjs
import fs from 'node:fs';
import { fileURLToPath, pathToFileURL } from 'node:url';
import path from 'node:path';

const here=path.dirname(fileURLToPath(import.meta.url));
const localPy=path.join(here,'porfirchik.py');
const runtimePath=path.join(here,'server.porfirchik-v21.mjs');
if(!fs.existsSync(localPy))throw new Error('Porfirchik V21: missing '+localPy);
let s=fs.readFileSync(path.join(here,'server.mjs'),'utf8');
const replaceOne=(from,to,label)=>{const n=s.split(from).length-1;if(n!==1)throw new Error('Porfirchik V21 anchor mismatch: '+label+' count='+n);s=s.replace(from,to);};
replaceOne(
  "const ND_PORFIRCHIK_GATEWAY_V20_7_4='porfirchik-v20.7.4-free-music-yandex-fallback-20260930';",
  "const ND_PORFIRCHIK_GATEWAY_V20_7_4='porfirchik-v21';",
  'revision'
);
replaceOne(
  "const PORFIRCHIK_SOURCE_COMMIT=",
  "const localPy="+JSON.stringify(localPy)+";\nconst PORFIRCHIK_SOURCE_COMMIT=",
  'local_path'
);
replaceOne(
  "\"s=urllib.request.urlopen(u,timeout=30).read()\",",
  "\"s=open(\"+JSON.stringify(localPy)+\",'rb').read()\",",
  'local_source'
);
fs.writeFileSync(runtimePath,s);
console.log('ND_PORFIRCHIK_V21_SHIM_READY');
await import(pathToFileURL(runtimePath).href);
