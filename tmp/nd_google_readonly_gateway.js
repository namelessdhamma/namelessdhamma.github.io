import { createPrivateKey, sign as rsaSign } from "node:crypto";

const PORT = Number(process.env.PORT || 3000);
const CLIENT_EMAIL = process.env.ND_GOOGLE_CLIENT_EMAIL || "";
const PRIVATE_KEY_B64 = process.env.ND_GOOGLE_PRIVATE_KEY_B64 || "";
const STATEHEAD_ID = process.env.ND_GOOGLE_STATEHEAD_ID || "1gB6zqJPsQQmv7cT3nxFOtM_EcrUqC3v_MN9ChymclOQ";
const AUTH = process.env.QSTASH_TOKEN || "";
const cache = { token: "", exp: 0, at: 0, state: null, registry: null };

function b64u(input) { return Buffer.from(input).toString("base64url"); }
async function accessToken() {
  const now = Math.floor(Date.now()/1000);
  if (cache.token && now < cache.exp - 120) return cache.token;
  if (!CLIENT_EMAIL || !PRIVATE_KEY_B64) throw new Error("google service-account env missing");
  const pem = Buffer.from(PRIVATE_KEY_B64, "base64").toString("utf8");
  const h = b64u(JSON.stringify({alg:"RS256",typ:"JWT"}));
  const p = b64u(JSON.stringify({iss:CLIENT_EMAIL,scope:"https://www.googleapis.com/auth/drive.readonly",aud:"https://oauth2.googleapis.com/token",iat:now,exp:now+3600}));
  const input = h+"."+p;
  const sig = rsaSign("RSA-SHA256", Buffer.from(input), createPrivateKey(pem)).toString("base64url");
  const body = new URLSearchParams({grant_type:"urn:ietf:params:oauth:grant-type:jwt-bearer",assertion:input+"."+sig});
  const r = await fetch("https://oauth2.googleapis.com/token",{method:"POST",headers:{"content-type":"application/x-www-form-urlencoded"},body});
  const t = await r.text();
  if (!r.ok) throw new Error("oauth "+r.status+": "+t.slice(0,300));
  const j=JSON.parse(t); cache.token=j.access_token; cache.exp=now+Number(j.expires_in||3600); return cache.token;
}
async function gfetch(url) {
  const tok=await accessToken();
  const r=await fetch(url,{headers:{Authorization:"Bearer "+tok,"User-Agent":"nd-google-readonly/1.0"}});
  if(!r.ok) throw new Error("google "+r.status+": "+(await r.text()).slice(0,400));
  return r;
}
async function meta(id) {
  const fields=encodeURIComponent("id,name,mimeType,modifiedTime,parents,webViewLink");
  return await (await gfetch("https://www.googleapis.com/drive/v3/files/"+encodeURIComponent(id)+"?supportsAllDrives=true&fields="+fields)).json();
}
async function textFile(id,m=null,max=12000) {
  m=m||await meta(id); const mt=m.mimeType||""; let u="";
  if(mt==="application/vnd.google-apps.document") u="https://www.googleapis.com/drive/v3/files/"+encodeURIComponent(id)+"/export?mimeType="+encodeURIComponent("text/plain");
  else if(mt==="application/vnd.google-apps.spreadsheet") u="https://www.googleapis.com/drive/v3/files/"+encodeURIComponent(id)+"/export?mimeType="+encodeURIComponent("text/csv");
  else if(mt==="application/json"||mt.startsWith("text/")||mt==="application/octet-stream") u="https://www.googleapis.com/drive/v3/files/"+encodeURIComponent(id)+"?alt=media&supportsAllDrives=true";
  else return "";
  return (await (await gfetch(u)).text()).slice(0,max);
}
async function jsonFile(id){ return JSON.parse((await textFile(id,null,1000000)).replace(/^\uFEFF/,"")); }
async function stateRegistry(){
  const now=Date.now();
  if(cache.state&&now-cache.at<180000) return [cache.state,cache.registry];
  const st=await jsonFile(STATEHEAD_ID), cr=st.capability_registry||{};
  if(!cr.canonical_artifact_id) throw new Error("statehead registry artifact missing");
  const rg=await jsonFile(cr.canonical_artifact_id);
  if(String(rg.version)!==String(cr.registry_version)) throw new Error("statehead/registry version mismatch");
  cache.state=st;cache.registry=rg;cache.at=now;return [st,rg];
}
function terms(q){
  const stop=new Set(["это","как","что","для","или","при","над","под","про","мне","тебе","можно","нужно","хочу","есть","the","and","for","with","from","this","that","have","what","about","into","your"]);
  return [...new Set((q.toLowerCase().match(/[a-zа-яё0-9_-]{3,}/giu)||[]).filter(x=>!stop.has(x)))].slice(0,10);
}
function scoreComp(c,ts,q){
  const blob=["component_key","semantic_id","version","exact_status","canonical_artifact_name","owner"].map(k=>String(c[k]||"")).join(" ").toLowerCase();
  let s=0;for(const t of ts)if(blob.includes(t))s+=5;
  const l=q.toLowerCase(),k=String(c.component_key||"").toLowerCase();
  if(/(исслед|research)/.test(l)&&/(true_research|pcpa|paccaya|dhamma|governing)/.test(k))s+=8;
  if(/(книг|рассказ|текст|литератур|write|book)/.test(l)&&/book/.test(k))s+=12;
  if(/(визуал|изображ|visual)/.test(l)&&/visual/.test(k))s+=12;
  if(/(архитект|architecture|система|system|state|памят|memory)/.test(l)&&/(system|working_architecture|storage|schema|interop)/.test(k))s+=10;
  if(/(скил|skill|capabil|способност)/.test(l)&&/skill/.test(blob))s+=8;
  return s;
}
async function bundleSummary(st){
  const latest=st?.durable_record_store?.latest_bundle||{};if(!latest.artifact_id)return "";
  try{
    const b=await jsonFile(latest.artifact_id);let cp=null,tx=null;
    for(const rr of (b.records||[])){const r=rr.record||{};if(r.record_type==="Checkpoint")cp=r;if(r.record_type==="TransactionRecord")tx=r;}
    const o={bundle_id:b.bundle_id,checkpoint_id:b.checkpoint_id,created_at:b.created_at};
    if(cp){o.active_frontier_ids=cp.active_frontier_ids;o.primary_frontier_question_id=cp.primary_frontier_question_id;o.model_id=cp.model_id;o.model_version=cp.model_version;o.latest_transaction_id=cp.latest_transaction_id;}
    if(tx){o.operation_mode=tx.operation_mode;o.changed_ids=tx.changed_ids;o.published_at=tx.published_at;}
    return JSON.stringify(o,null,2);
  }catch(e){return "Latest durable bundle unavailable: "+String(e).slice(0,300);}
}
async function discovery(q){
  if(!/(plugin|плагин|tool|инструмент|agent|агент|automation|автомат|connector|подключ)/i.test(q))return [];
  const ts=terms(q),focus=ts[0]||"ND",escaped=focus.replaceAll("'","\\'");
  const params=new URLSearchParams({q:"trashed=false and fullText contains '"+escaped+"'",pageSize:"8",orderBy:"modifiedTime desc",fields:"files(id,name,mimeType,modifiedTime,webViewLink)",supportsAllDrives:"true",includeItemsFromAllDrives:"true"});
  try{
    const j=await (await gfetch("https://www.googleapis.com/drive/v3/files?"+params)).json(),out=[];
    for(const f of (j.files||[]).slice(0,2)){const t=await textFile(f.id,f,3200).catch(()=> "");if(t.trim())out.push({label:"Google Drive NON-AUTHORITATIVE discovery: "+f.name,text:t,authority:"NON_AUTH"});}
    return out;
  }catch(e){return [];}
}
async function context(q){
  const [st,rg]=await stateRegistry(),cr=st.capability_registry||{},comps=rg.components||[],ts=terms(q);
  const sh={record_type:st.record_type,status:st.status,head_id:st.head_id,published_at:st.published_at,registry_id:cr.registry_id,registry_version:cr.registry_version,registry_artifact_id:cr.canonical_artifact_id,durable_store:st?.durable_record_store?.store_id};
  const cap=comps.map(c=>c.component_key+" | "+c.semantic_id+" v"+c.version+" | "+c.exact_status+" | read="+(c.read_permissions||[]).join(",").slice(0,160)+" | write="+(c.write_permissions||[]).join(",").slice(0,160)).join("\n");
  const pieces=[{label:"Google Drive AUTHORITATIVE StateHead",text:JSON.stringify(sh,null,2),authority:"AUTHORITATIVE"},{label:"Google Drive AUTHORITATIVE Capability Registry v"+rg.version,text:cap.slice(0,9000),authority:"AUTHORITATIVE"}];
  const mem=await bundleSummary(st);if(mem)pieces.push({label:"Google Drive AUTHORITATIVE durable memory summary",text:mem.slice(0,5000),authority:"AUTHORITATIVE"});
  const ranked=comps.map(c=>[scoreComp(c,ts,q),c]).sort((a,b)=>b[0]-a[0]);let n=0;
  for(const [s,c] of ranked){if(s<=0||n>=2)break;if(!c.canonical_artifact_id)continue;try{const m=await meta(c.canonical_artifact_id),t=await textFile(c.canonical_artifact_id,m,5200);if(t.trim()){pieces.push({label:"Google Drive CANONICAL "+c.component_key+" | "+c.semantic_id+" v"+c.version+" | "+c.exact_status,text:t,authority:"CANONICAL"});n++;}}catch(e){}}
  pieces.push(...await discovery(q));
  return {statehead_status:st.status,registry_version:rg.version,component_count:comps.length,selected_components:n,pieces};
}
function authorized(req){return !!AUTH&&(req.headers.get("authorization")||"")==="Bearer "+AUTH;}
async function handler(req){
  const u=new URL(req.url);
  if(u.pathname==="/health")return Response.json({ok:true,service:"ND Google Read-Only Authority Gateway"});
  if(u.pathname==="/nd/context"){
    if(req.method!=="GET")return new Response("method not allowed",{status:405});
    if(!authorized(req))return new Response("unauthorized",{status:401});
    try{return Response.json(await context((u.searchParams.get("q")||"ND architecture").slice(0,6000)));}
    catch(e){console.error("ND_GOOGLE_CONTEXT_ERROR",String(e).slice(0,700));return Response.json({error:"context_unavailable"},{status:503});}
  }
  return new Response("not found",{status:404});
}
Bun.serve({port:PORT,fetch:handler});
console.log("ND_GOOGLE_READONLY_GATEWAY_START",JSON.stringify({port:PORT,statehead_id:STATEHEAD_ID,client:!!CLIENT_EMAIL,key:!!PRIVATE_KEY_B64,mutations:false}));
setTimeout(async()=>{try{const [s,r]=await stateRegistry();console.log("ND_GOOGLE_GATEWAY_PROBE",JSON.stringify({ok:true,statehead_status:s.status,registry_version:r.version,components:(r.components||[]).length,mutations:false}));}catch(e){console.error("ND_GOOGLE_GATEWAY_PROBE",JSON.stringify({ok:false,error:String(e).slice(0,600),mutations:false}));}},1000);
