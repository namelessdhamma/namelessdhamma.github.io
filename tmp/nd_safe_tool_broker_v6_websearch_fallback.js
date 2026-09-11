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
const serveMarker='Bun.serve({port:PORT,fetch:handler});';
if(!patched.includes(serveMarker))throw new Error('serve marker missing');
const selfProbeCode="setTimeout(async()=>{\n  const tests=[[\"nd_authority\",\"Current ND StateHead Registry System Skill architecture\"],[\"google_drive_search\",\"True Research canonical skill\"],[\"github_read\",\"current ND architecture decisions Recent Changes\"],[\"web_current\",\"Find the latest official OpenAI ChatGPT release notes update. Use official OpenAI sources and return direct URL and date.\"]];\n  for(const [tool,q] of tests){\n    const t=Date.now();\n    try{\n      const r=await invokeTool(tool,q);\n      const m={tool,ok:true,elapsed_ms:Date.now()-t,mutations:false};\n      if(tool===\"nd_authority\"){m.statehead_status=r?.statehead_status;m.registry_version=r?.registry_version;m.component_count=r?.component_count;m.pieces=(r?.pieces||[]).length;}\n      if(tool===\"google_drive_search\")m.results=(r?.results||[]).length;\n      if(tool===\"github_read\"){m.repo=r?.repo;m.results=(r?.results||[]).length;m.wikilinks=!!r?.followed_wikilinks;}\n      if(tool===\"web_current\"){m.source_urls=(r?.source_urls||[]).length;m.verified_search=!!r?.verified_search;m.tool_calls=r?.tool_calls||0;}\n      console.log(\"ND_BROKER_SELF_PROBE\",JSON.stringify(m));\n    }catch(e){console.error(\"ND_BROKER_SELF_PROBE\",JSON.stringify({tool,ok:false,error:String(e).slice(0,350),mutations:false}));}\n  }\n},2500);";
patched=patched.replace(serveMarker,serveMarker+'\n'+selfProbeCode);
const encoded=Buffer.from(patched).toString('base64');
await import('data:text/javascript;base64,'+encoded);
