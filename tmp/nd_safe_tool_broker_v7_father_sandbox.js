const BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/46de9fcfa1f0c44863e9dd491d480e8e5160aca4/tmp/nd_safe_tool_broker_v2.js';
const src=await (await fetch(BASE)).text();
const start=src.indexOf('async function webCurrent(q){');
const end=src.indexOf('async function invokeTool(name,q){',start);
if(start<0||end<0)throw new Error('webCurrent block not found');
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
      const r=await fetch("https://api.groq.com/openai/v1/chat/completions",{method:"POST",headers:{Authorization:"Bearer "+GROQ_API_KEY,"Content-Type":"application/json","Groq-Model-Version":"latest","User-Agent":"nd-safe-tool-broker/6.0"},body:JSON.stringify(payload)});
      const t=await r.text();
      if(r.ok){
        const j=JSON.parse(t),msg=j.choices?.[0]?.message||{},exec=msg.executed_tools||[];
        const names=exec.map(x=>String(x?.type||x?.name||x?.tool_name||"").toLowerCase());
        if(!exec.length||!names.some(x=>x.includes("web_search")||x.includes("search"))){lastErr="web verification used no search tool";break;}
        const urls=[];const blob=JSON.stringify(exec)+" "+String(msg.content||"");
        for(const m of blob.matchAll(/https?:\/\/[^\s"\'<>]+/g)){const u=m[0].replace(/[).,;\]]+$/,"");if(!urls.includes(u))urls.push(u);if(urls.length>=10)break;}
        if(!urls.length){lastErr="web verification returned no source URLs";break;}
        return {brief:String(msg.content||"").trim().slice(0,6500),source_urls:urls,tool_calls:exec.length,verified_search:true,model,query_chars:query.length,mutations:false};
      }
      lastErr="groq "+r.status+": "+t.slice(0,300);
      if(r.status===429&&attempt===0){await new Promise(res=>setTimeout(res,1500));continue;}
      break;
    }
  }
  throw new Error(lastErr||"web verification failed");
}`;
let patched=src.slice(0,start)+compact+src.slice(end);
const SB_REV="1a438fbf993e40f2d209fe9f455be447ce302ca6";
const SB_BASE="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/"+SB_REV+"/tmp/";
const sbFrag=await (await fetch(SB_BASE+"nd_father_sandbox_inject_v1.jsfrag")).text();
const sbProbe=await (await fetch(SB_BASE+"nd_father_sandbox_selfprobe_v1.jsfrag")).text();
patched=patched.replace('import { createPrivateKey, sign as rsaSign } from "node:crypto";','import { createPrivateKey, createHash, sign as rsaSign } from "node:crypto";');
patched=patched.replace("https://www.googleapis.com/auth/drive.readonly","https://www.googleapis.com/auth/drive");
const sbInvokeMarker="async function invokeTool(name,q){";
if(!patched.includes(sbInvokeMarker))throw new Error("sandbox invoke marker missing");
patched=patched.replace(sbInvokeMarker,sbFrag+"\\n"+"async function invokeTool(name,q,args={}){\\n  if(name===\"sandbox_create\")return await sandboxCreate(args);\\n  if(name===\"sandbox_update\")return await sandboxUpdate(args);\\n  if(name===\"sandbox_read\")return await sandboxRead(args);\\n  if(name===\"sandbox_list\")return await sandboxList(args);\\n  if(name===\"sandbox_inbox_submit\")return await sbSemantic(args,FATHER_FOLDERS.inbox,\"INBOX_WORK_ITEM\",\"RECEIVED\");\\n  if(name===\"sandbox_book_draft\")return await sbSemantic(args,FATHER_FOLDERS.book_drafts,\"BOOK_DRAFT\",\"PROPOSED / NON-CANONICAL\");\\n  if(name===\"sandbox_research_save\")return await sbSemantic(args,FATHER_FOLDERS.research,\"RESEARCH_ARTIFACT\",\"READY_FOR_REVIEW\");\\n  if(name===\"sandbox_shared_note\")return await sbSemantic(args,FATHER_FOLDERS.shared_notes,\"SHARED_NOTE\",\"NON-CANONICAL\");");
const sbOldHandler="const j=await req.json();const tool=String(j.tool||\"\").slice(0,80),q=String(j.query||\"\").slice(0,9000),t=Date.now();\\n      const result=await invokeTool(tool,q);\\n      console.log(\"BROKER_INVOKE\",JSON.stringify({tool,ok:true,elapsed_ms:Date.now()-t,result_chars:JSON.stringify(result).length,mutations:false}));\\n      return Response.json({meta:{tool,ok:true,elapsed_ms:Date.now()-t,mutations:false},result});";
const sbNewHandler="const j=await req.json();const tool=String(j.tool||\"\").slice(0,80),q=String(j.query||\"\").slice(0,9000),args=(j.args&&typeof j.args===\"object\")?j.args:{},t=Date.now();\\n      const result=await invokeTool(tool,q,args);\\n      const sandbox_mutation=[\"sandbox_create\",\"sandbox_update\",\"sandbox_inbox_submit\",\"sandbox_book_draft\",\"sandbox_research_save\",\"sandbox_shared_note\"].includes(tool);\\n      console.log(\"BROKER_INVOKE\",JSON.stringify({tool,ok:true,elapsed_ms:Date.now()-t,result_chars:JSON.stringify(result).length,canonical_mutations:false,sandbox_mutation}));\\n      return Response.json({meta:{tool,ok:true,elapsed_ms:Date.now()-t,canonical_mutations:false,sandbox_mutation},result});";
if(!patched.includes(sbOldHandler))throw new Error("sandbox handler marker missing");
patched=patched.replace(sbOldHandler,sbNewHandler);
patched=patched.replace('service:"ND Safe Tool Broker v2 + Google Authority",mode:"READ_ONLY",mutations:false','service:"ND Safe Tool Broker v7 + Father Sandbox",mode:"BOUNDED_WRITE_SANDBOX",canonical_mutations:false,sandbox_mutations:true');
patched=patched.replace('console.log("ND_SAFE_TOOL_BROKER_START",JSON.stringify({port:PORT,statehead_id:STATEHEAD_ID,google:!!CLIENT_EMAIL&&!!PRIVATE_KEY_B64,github:!!GITHUB_TOKEN,web:!!GROQ_API_KEY,mutations:false}));','console.log("ND_SAFE_TOOL_BROKER_V7_FATHER_SANDBOX_START",JSON.stringify({port:PORT,statehead_id:STATEHEAD_ID,google:!!CLIENT_EMAIL&&!!PRIVATE_KEY_B64,github:!!GITHUB_TOKEN,web:!!GROQ_API_KEY,canonical_mutations:false,sandbox_mutations:true,father_root:FATHER_ROOT_ID}));');
const sbServe="Bun.serve({port:PORT,fetch:handler});";
if(!patched.includes(sbServe))throw new Error("sandbox serve marker missing");
patched=patched.replace(sbServe,sbServe+"\\n"+sbProbe);
const serveMarker='Bun.serve({port:PORT,fetch:handler});';
if(!patched.includes(serveMarker))throw new Error('serve marker missing');
const selfProbeCode="setTimeout(async()=>{\n  const tests=[[\"nd_authority\",\"Current ND StateHead Registry System Skill architecture\"],[\"google_drive_search\",\"True Research canonical skill\"],[\"github_read\",\"current ND architecture decisions Recent Changes\"],[\"web_current\",\"Find the latest official OpenAI ChatGPT release notes update. Use official OpenAI sources and return direct URL and date.\"]];\n  for(const [tool,q] of tests){\n    const t=Date.now();\n    try{\n      const r=await invokeTool(tool,q);\n      const m={tool,ok:true,elapsed_ms:Date.now()-t,mutations:false};\n      if(tool===\"nd_authority\"){m.statehead_status=r?.statehead_status;m.registry_version=r?.registry_version;m.component_count=r?.component_count;m.pieces=(r?.pieces||[]).length;}\n      if(tool===\"google_drive_search\")m.results=(r?.results||[]).length;\n      if(tool===\"github_read\"){m.repo=r?.repo;m.results=(r?.results||[]).length;m.wikilinks=!!r?.followed_wikilinks;}\n      if(tool===\"web_current\"){m.source_urls=(r?.source_urls||[]).length;m.verified_search=!!r?.verified_search;m.tool_calls=r?.tool_calls||0;}\n      console.log(\"ND_BROKER_SELF_PROBE\",JSON.stringify(m));\n    }catch(e){console.error(\"ND_BROKER_SELF_PROBE\",JSON.stringify({tool,ok:false,error:String(e).slice(0,350),mutations:false}));}\n  }\n},2500);";
patched=patched.replace(serveMarker,serveMarker+'\n'+selfProbeCode);
const encoded=Buffer.from(patched).toString('base64');
await import('data:text/javascript;base64,'+encoded);
