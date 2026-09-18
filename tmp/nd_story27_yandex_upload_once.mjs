import { createHash } from "node:crypto";

const BASE="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/b17d40b9aae850250a1781affbdd51506652dacf/tmp/nd_yandex_youtube_mux_mcp_v01.mjs";
const TOKEN=String(process.env.YANDEX_DISK_TOKEN||"").trim();
const TARGET=String(process.env.ND_STORY27_TARGET||"").trim();
const TEXT_B64=String(process.env.ND_STORY27_TEXT_B64||"").trim();
const REV=String(process.env.ND_STORY27_UPLOAD_REV||"").trim();
const API="https://cloud-api.yandex.net/v1/disk";

function esc(s){return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}
const crcTable=(()=>{const t=new Uint32Array(256);for(let n=0;n<256;n++){let c=n;for(let k=0;k<8;k++)c=(c&1)?0xEDB88320^(c>>>1):c>>>1;t[n]=c>>>0;}return t;})();
function crc32(buf){let c=0xFFFFFFFF;for(const b of buf)c=crcTable[(c^b)&255]^(c>>>8);return (c^0xFFFFFFFF)>>>0;}
function u16(n){const b=Buffer.alloc(2);b.writeUInt16LE(n);return b;} function u32(n){const b=Buffer.alloc(4);b.writeUInt32LE(n>>>0);return b;}
function zipStore(entries){
  const locals=[],centrals=[]; let offset=0;
  for(const [name,data0] of entries){
    const nameB=Buffer.from(name),data=Buffer.isBuffer(data0)?data0:Buffer.from(data0);
    const crc=crc32(data);
    const local=Buffer.concat([u32(0x04034b50),u16(20),u16(0),u16(0),u16(0),u16(0),u32(crc),u32(data.length),u32(data.length),u16(nameB.length),u16(0),nameB,data]);
    locals.push(local);
    const central=Buffer.concat([u32(0x02014b50),u16(20),u16(20),u16(0),u16(0),u16(0),u16(0),u32(crc),u32(data.length),u32(data.length),u16(nameB.length),u16(0),u16(0),u16(0),u16(0),u32(0),u32(offset),nameB]);
    centrals.push(central); offset+=local.length;
  }
  const cd=Buffer.concat(centrals), body=Buffer.concat(locals);
  const eocd=Buffer.concat([u32(0x06054b50),u16(0),u16(0),u16(entries.length),u16(entries.length),u32(cd.length),u32(body.length),u16(0)]);
  return Buffer.concat([body,cd,eocd]);
}
function docx(text){
  const paras=text.split(/\n/).map(line=>`<w:p><w:r><w:t xml:space="preserve">${esc(line)}</w:t></w:r></w:p>`).join("");
  const ct='<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>';
  const rels='<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>';
  const doc=`<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>${paras}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr></w:body></w:document>`;
  return zipStore([["[Content_Types].xml",ct],["_rels/.rels",rels],["word/document.xml",doc]]);
}
async function api(endpoint,q={},method="GET"){
  const u=new URL(API+endpoint); for(const[k,v]of Object.entries(q))u.searchParams.set(k,String(v));
  const r=await fetch(u,{method,headers:{Authorization:"OAuth "+TOKEN,Accept:"application/json","User-Agent":"nd-story27-once/1.0"}});
  const t=await r.text(); const d=t?JSON.parse(t):{}; if(!r.ok)throw new Error("api_"+r.status+":"+(d.message||"request_failed")); return d;
}
function readStored(buf,name){
  let p=0;
  while(p+30<=buf.length && buf.readUInt32LE(p)===0x04034b50){
    const method=buf.readUInt16LE(p+8), size=buf.readUInt32LE(p+18), nlen=buf.readUInt16LE(p+26), xlen=buf.readUInt16LE(p+28);
    const nm=buf.subarray(p+30,p+30+nlen).toString("utf8"), start=p+30+nlen+xlen;
    if(nm===name){if(method!==0)throw new Error("unexpected_compression");return buf.subarray(start,start+size);}
    p=start+size;
  }
  throw new Error("entry_not_found:"+name);
}
async function once(){
  if(!TOKEN||!TARGET||!TEXT_B64||!REV) throw new Error("story27_once_missing_env");
  const text=Buffer.from(TEXT_B64,"base64").toString("utf8");
  const before=await api("/resources",{path:TARGET,limit:1});
  const bytes=docx(text), sha=createHash("sha256").update(bytes).digest("hex");
  const up=await api("/resources/upload",{path:TARGET,overwrite:"true"});
  const put=await fetch(up.href,{method:"PUT",headers:{"Content-Type":"application/vnd.openxmlformats-officedocument.wordprocessingml.document","Content-Length":String(bytes.length)},body:bytes});
  if(!put.ok)throw new Error("upload_"+put.status);
  await new Promise(r=>setTimeout(r,1200));
  const after=await api("/resources",{path:TARGET,limit:1});
  const dl=await api("/resources/download",{path:TARGET}); const rr=await fetch(dl.href); const got=Buffer.from(await rr.arrayBuffer());
  const xml=readStored(got,"word/document.xml").toString("utf8");
  const checks={
    title:xml.includes("Не мой приказ"),
    lifetime:xml.includes("По содержанию — на целую жизнь."),
    qs_place:xml.includes("Q.S., в акте управления:"),
    qs_tea:xml.includes("Если мысль пришла без приглашения, это ещё не значит, что ей нужно предлагать чай."),
    qs_sign:xml.includes("Подпись управлявшего: __________"),
    qs_alts:xml.includes("Q.S. — другие варианты для выбора")
  };
  const gotSha=createHash("sha256").update(got).digest("hex");
  console.log("ND_STORY27_UPLOAD_RESULT",JSON.stringify({rev:REV,target:TARGET,before_md5:before.md5||null,after_md5:after.md5||null,before_size:before.size||null,after_size:after.size||null,local_sha256:sha,download_sha256:gotSha,valid_docx:got.slice(0,2).toString("ascii")==="PK"&&Object.values(checks).every(Boolean),checks,public_url:after.public_url||null}));
}
console.log("ND_STORY27_BOOT",JSON.stringify({token:Boolean(TOKEN),target:TARGET,text_b64_len:TEXT_B64.length,rev:REV}));
try{await once();}catch(e){console.log("ND_STORY27_UPLOAD_FAILED",String(e?.message||e).slice(0,1200));}
const base=await (await fetch(BASE)).text(); await import("data:text/javascript;base64,"+Buffer.from(base).toString("base64"));