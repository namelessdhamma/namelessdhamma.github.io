const BASE="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/b17d40b9aae850250a1781affbdd51506652dacf/tmp/nd_yandex_youtube_mux_mcp_v01.mjs";
let src=await (await fetch(BASE)).text();
const helper=String.raw`
const STORY27_TRIGGER=String(process.env.ND_STORY27_TRIGGER||"").trim();
const STORY27_PATH=STORY27_TRIGGER?"/story27-once/"+STORY27_TRIGGER:"";
const STORY27_TARGET=String(process.env.ND_STORY27_TARGET||"").trim();
const STORY27_TEXT_B64=String(process.env.ND_STORY27_TEXT_B64||"").trim();
const STORY27_REV=String(process.env.ND_STORY27_UPLOAD_REV||"").trim();
const S27_CRC_TABLE=(()=>{const t=new Uint32Array(256);for(let n=0;n<256;n++){let c=n;for(let k=0;k<8;k++)c=(c&1)?0xEDB88320^(c>>>1):c>>>1;t[n]=c>>>0;}return t;})();
function s27crc(buf){let c=0xFFFFFFFF;for(const b of buf)c=S27_CRC_TABLE[(c^b)&255]^(c>>>8);return (c^0xFFFFFFFF)>>>0;}
function s27u16(n){const b=Buffer.alloc(2);b.writeUInt16LE(n);return b;}
function s27u32(n){const b=Buffer.alloc(4);b.writeUInt32LE(n>>>0);return b;}
function s27esc(s){return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}
function s27zip(entries){
 const locals=[],centrals=[];let offset=0;
 for(const [name,data0] of entries){
  const nameB=Buffer.from(name),data=Buffer.isBuffer(data0)?data0:Buffer.from(data0),crc=s27crc(data);
  const local=Buffer.concat([s27u32(0x04034b50),s27u16(20),s27u16(0),s27u16(0),s27u16(0),s27u16(0),s27u32(crc),s27u32(data.length),s27u32(data.length),s27u16(nameB.length),s27u16(0),nameB,data]);
  locals.push(local);
  centrals.push(Buffer.concat([s27u32(0x02014b50),s27u16(20),s27u16(20),s27u16(0),s27u16(0),s27u16(0),s27u16(0),s27u32(crc),s27u32(data.length),s27u32(data.length),s27u16(nameB.length),s27u16(0),s27u16(0),s27u16(0),s27u16(0),s27u32(0),s27u32(offset),nameB]));
  offset+=local.length;
 }
 const body=Buffer.concat(locals),cd=Buffer.concat(centrals);
 return Buffer.concat([body,cd,s27u32(0x06054b50),s27u16(0),s27u16(0),s27u16(entries.length),s27u16(entries.length),s27u32(cd.length),s27u32(body.length),s27u16(0)]);
}
function s27docx(text){
 const paras=text.split(/\n/).map(line=>'<w:p><w:r><w:t xml:space="preserve">'+s27esc(line)+'</w:t></w:r></w:p>').join("");
 const ct='<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>';
 const rels='<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>';
 const doc='<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'+paras+'<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr></w:body></w:document>';
 return s27zip([["[Content_Types].xml",ct],["_rels/.rels",rels],["word/document.xml",doc]]);
}
function s27read(buf,name){
 let p=0;
 while(p+30<=buf.length&&buf.readUInt32LE(p)===0x04034b50){
  const method=buf.readUInt16LE(p+8),size=buf.readUInt32LE(p+18),nlen=buf.readUInt16LE(p+26),xlen=buf.readUInt16LE(p+28);
  const nm=buf.subarray(p+30,p+30+nlen).toString("utf8"),start=p+30+nlen+xlen;
  if(nm===name){if(method!==0)throw new Error("unexpected_compression");return buf.subarray(start,start+size);}
  p=start+size;
 }
 throw new Error("entry_not_found:"+name);
}
async function s27run(){
 if(!TOKEN||!STORY27_TARGET||!STORY27_TEXT_B64||!STORY27_REV)throw new Error("story27_missing_env");
 const text=Buffer.from(STORY27_TEXT_B64,"base64").toString("utf8");
 const before=await api("/resources",{path:STORY27_TARGET,limit:1});
 const bytes=s27docx(text);
 const up=await api("/resources/upload",{path:STORY27_TARGET,overwrite:"true"});
 const put=await fetch(up.href,{method:"PUT",headers:{"Content-Type":"application/vnd.openxmlformats-officedocument.wordprocessingml.document","Content-Length":String(bytes.length)},body:bytes});
 if(!put.ok)throw new Error("upload_http_"+put.status);
 await new Promise(r=>setTimeout(r,1200));
 const after=await api("/resources",{path:STORY27_TARGET,limit:1});
 const dl=await api("/resources/download",{path:STORY27_TARGET});const rr=await fetch(dl.href);if(!rr.ok)throw new Error("readback_http_"+rr.status);
 const got=Buffer.from(await rr.arrayBuffer()),xml=s27read(got,"word/document.xml").toString("utf8");
 const checks={
  title:xml.includes("Не мой приказ"),
  lifetime:xml.includes("По содержанию — на целую жизнь."),
  qs_place:xml.includes("Q.S., в акте управления:"),
  qs_tea:xml.includes("Если мысль пришла без приглашения, это ещё не значит, что ей нужно предлагать чай."),
  qs_sign:xml.includes("Подпись управлявшего: __________"),
  qs_alts:xml.includes("Q.S. — другие варианты для выбора")
 };
 return {ok:true,rev:STORY27_REV,target:STORY27_TARGET,before_md5:before.md5||null,after_md5:after.md5||null,before_size:before.size||null,after_size:after.size||null,valid_docx:got.slice(0,2).toString("ascii")==="PK"&&Object.values(checks).every(Boolean),checks,public_url:after.public_url||null};
}
`;
const marker="const muxServer=http.createServer(async(req,res)=>{";
if(!src.includes(marker))throw new Error("mux marker missing");
src=src.replace(marker,helper+"\n"+marker);
const routeMarker="    const path=new URL(req.url||'/','http://local').pathname;\n";
const route=`    if(STORY27_PATH && path===STORY27_PATH){\n      if(req.method!=="POST") return j(res,405,{ok:false,error:"method_not_allowed"});\n      try{return j(res,200,await s27run());}catch(e){return j(res,500,{ok:false,error:String(e?.message||e).slice(0,1200)});}\n    }\n`;
if(!src.includes(routeMarker))throw new Error("path marker missing");
src=src.replace(routeMarker,routeMarker+route);
await import("data:text/javascript;base64,"+Buffer.from(src).toString("base64"));