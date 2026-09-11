const BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/46de9fcfa1f0c44863e9dd491d480e8e5160aca4/tmp/nd_safe_tool_broker_v2.js';
const src=await (await fetch(BASE)).text();

const webStart=src.indexOf('async function webCurrent(q){');
const webEnd=src.indexOf('async function invokeTool(name,q){',webStart);
if(webStart<0||webEnd<0)throw new Error('webCurrent block not found');
const compact=String.raw`async function webCurrent(q){
  if(!GROQ_API_KEY)throw new Error("groq research unavailable");
  const today=new Date().toISOString().slice(0,10);
  const raw=String(q||"").replace(/\s+/g," ").trim();
  if(!raw)throw new Error("empty web research query");
  const query=("Today is "+today+". Search the current web for this request. Prefer official/primary and recent sources. Return direct source URLs and dates. Request: "+raw).slice(0,900);
  const models=["groq/compound-mini","groq/compound"];
  let lastErr="";
  for(const model of models){
    const payload={model,messages:[{role:"user",content:query}],compound_custom:{tools:{enabled_tools:["web_search"]}}};
    for(let attempt=0;attempt<2;attempt++){
      const r=await fetch("https://api.groq.com/openai/v1/chat/completions",{method:"POST",headers:{Authorization:"Bearer "+GROQ_API_KEY,"Content-Type":"application/json","Groq-Model-Version":"latest","User-Agent":"nd-safe-tool-broker/7.0"},body:JSON.stringify(payload)});
      const t=await r.text();
      if(r.ok){
        const j=JSON.parse(t),msg=j.choices?.[0]?.message||{},exec=msg.executed_tools||[];
        const names=exec.map(x=>String(x?.type||x?.name||x?.tool_name||"").toLowerCase());
        if(!exec.length||!names.some(x=>x.includes("web_search")||x.includes("search"))){lastErr="web verification used no search tool";break;}
        const urls=[];const blob=JSON.stringify(exec)+" "+String(msg.content||"");
        for(const m of blob.matchAll(/https?:\/\/[^\s"'<>]+/g)){const u=m[0].replace(/[).,;\]]+$/,"" );if(!urls.includes(u))urls.push(u);if(urls.length>=10)break;}
        if(!urls.length){lastErr="web verification returned no source URLs";break;}
        return {brief:String(msg.content||"").trim().slice(0,6500),source_urls:urls,tool_calls:exec.length,verified_search:true,model,query_chars:query.length,mutations:false};
      }
      lastErr="groq "+r.status+": "+t.slice(0,300);
      if(r.status===429&&attempt===0){await new Promise(res=>setTimeout(res,1500));continue;}
      break;
    }
  }
  throw new Error(lastErr||"web verification failed");
}
`;

let patched=src.slice(0,webStart)+compact+src.slice(webEnd);

const invokeMarker='async function invokeTool(name,q){';
if(!patched.includes(invokeMarker))throw new Error('invoke marker missing');

const sandboxCode=String.raw`
const FATHER_WORKSPACE={
  root:"1N7rXBuBg4Z8_35GXcjSC-F0snf37L0rL",
  inbox:"1LzNiq6PbE7yNZQqnHxexVbMkDpvI56Zl",
  book_drafts:"1aQ8cnGd423elt90t8vPjcPvp0x08oiFn",
  research:"1VksG2jZF6GjJUGPBspXwSTAtdQIx01S8",
  outbox:"1FfZS1jmrRF-BiCnzPnSqoD_2KHUzzGE8",
  shared_notes:"1cF1qB25BZPKmtvgoXXkSMrEh_LnYJiRD"
};
const FATHER_ALLOWED_FOLDER_IDS=new Set(Object.values(FATHER_WORKSPACE));
async function sandboxAccessToken(){
  const now=Math.floor(Date.now()/1000);
  if(!CLIENT_EMAIL||!PRIVATE_KEY_B64)throw new Error("google service-account env missing");
  const pem=Buffer.from(PRIVATE_KEY_B64,"base64").toString("utf8");
  const h=b64u(JSON.stringify({alg:"RS256",typ:"JWT"}));
  const p=b64u(JSON.stringify({iss:CLIENT_EMAIL,scope:"https://www.googleapis.com/auth/drive",aud:"https://oauth2.googleapis.com/token",iat:now,exp:now+900}));
  const input=h+"."+p;
  const sig=rsaSign("RSA-SHA256",Buffer.from(input),createPrivateKey(pem)).toString("base64url");
  const body=new URLSearchParams({grant_type:"urn:ietf:params:oauth:grant-type:jwt-bearer",assertion:input+"."+sig});
  const r=await fetch("https://oauth2.googleapis.com/token",{method:"POST",headers:{"content-type":"application/x-www-form-urlencoded"},body});
  const t=await r.text();
  if(!r.ok)throw new Error("sandbox oauth "+r.status+": "+t.slice(0,240));
  return JSON.parse(t).access_token;
}
async function sandboxMeta(id,tok){
  const fields=encodeURIComponent("id,name,mimeType,parents,capabilities(canAddChildren,canEdit,canMoveItemWithinDrive,canDelete)");
  const r=await fetch("https://www.googleapis.com/drive/v3/files/"+encodeURIComponent(id)+"?supportsAllDrives=true&fields="+fields,{headers:{Authorization:"Bearer "+tok,"User-Agent":"nd-safe-tool-broker/7.0"}});
  const t=await r.text();
  if(!r.ok)throw new Error("sandbox meta "+r.status+": "+t.slice(0,240));
  return JSON.parse(t);
}
async function sandboxQualification(){
  const tok=await sandboxAccessToken();
  const result={service_account:CLIENT_EMAIL,root_id:FATHER_WORKSPACE.root,folders:{},canonical_mutations:false,sandbox_mutations:false};
  for(const [key,id] of Object.entries(FATHER_WORKSPACE)){
    try{
      const m=await sandboxMeta(id,tok);
      const parentOk=key==="root"?true:(Array.isArray(m.parents)&&m.parents.includes(FATHER_WORKSPACE.root));
      const folderOk=m.mimeType==="application/vnd.google-apps.folder";
      const noShortcut=m.mimeType!=="application/vnd.google-apps.shortcut";
      result.folders[key]={id:m.id,name:m.name,folder:folderOk,parent_ok:parentOk,no_shortcut:noShortcut,can_add_children:!!m.capabilities?.canAddChildren,can_edit:!!m.capabilities?.canEdit};
    }catch(e){
      result.folders[key]={id,accessible:false,error:String(e).slice(0,240)};
    }
  }
  result.ready_for_write=Object.values(result.folders).every(x=>x.folder&&x.parent_ok&&x.no_shortcut&&x.can_add_children);
  return result;
}
`;

patched=patched.replace(invokeMarker,sandboxCode+'\n'+invokeMarker);

const healthOld='if(u.pathname==="/health")return Response.json({ok:true,service:"ND Safe Tool Broker v2 + Google Authority",mode:"READ_ONLY",mutations:false});';
const healthNew='if(u.pathname==="/health")return Response.json({ok:true,service:"ND Safe Tool Broker v7 sandbox qualification",mode:"READ_ONLY_CANONICAL",mutations:false,sandbox_mutations:false});';
if(!patched.includes(healthOld))throw new Error('health marker missing');
patched=patched.replace(healthOld,healthNew);

const authMarker='if(u.pathname==="/catalog"&&req.method==="GET")return Response.json(TOOL_CATALOG);';
if(!patched.includes(authMarker))throw new Error('auth marker missing');
patched=patched.replace(authMarker,authMarker+'\n  if(u.pathname==="/sandbox/qualify"&&req.method==="GET"){try{return Response.json(await sandboxQualification());}catch(e){console.error("ND_SANDBOX_QUALIFY",String(e).slice(0,500));return Response.json({error:"sandbox_qualification_failed",canonical_mutations:false,sandbox_mutations:false},{status:503});}}');

const serveMarker='Bun.serve({port:PORT,fetch:handler});';
if(!patched.includes(serveMarker))throw new Error('serve marker missing');
const probe=String.raw`
setTimeout(async()=>{
  try{
    const q=await sandboxQualification();
    console.log("ND_SANDBOX_QUALIFY",JSON.stringify({ok:true,service_account:q.service_account,ready_for_write:q.ready_for_write,folders:q.folders,canonical_mutations:false,sandbox_mutations:false}));
  }catch(e){
    console.error("ND_SANDBOX_QUALIFY",JSON.stringify({ok:false,error:String(e).slice(0,500),canonical_mutations:false,sandbox_mutations:false}));
  }
},1800);
`;
patched=patched.replace(serveMarker,serveMarker+'\n'+probe);

const encoded=Buffer.from(patched).toString('base64');
await import('data:text/javascript;base64,'+encoded);
