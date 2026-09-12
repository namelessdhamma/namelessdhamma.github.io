console.log('ND_SAFE_TOOL_BROKER_V9H_WRAPPER_START');
const BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/1c01b3551cdce1997c46aa81dd2ae4c72a551b72/tmp/nd_safe_tool_broker_v9b_web_resilient.js';
let src=await (await fetch(BASE)).text();
const start=src.indexOf('async function webCurrent(q){');
const end=src.indexOf('async function invokeTool(name,q){',start);
if(start<0||end<0)throw new Error('v9h webCurrent boundary missing');
const fn=`async function webCurrent(q){
 if(!GROQ_API_KEY)throw new Error("groq research unavailable");
 const today=new Date().toISOString().slice(0,10);
 const raw=String(q||"").replace(/\\s+/g," ").trim();
 if(!raw)throw new Error("empty web research query");
 const query=("Today "+today+". Search web now. Answer briefly and include 3 direct source URLs with dates. Q: "+raw.slice(0,260)).slice(0,380);
 const payload={model:"groq/compound-mini",messages:[{role:"user",content:query}],max_completion_tokens:700,compound_custom:{tools:{enabled_tools:["web_search"]}}};
 let last="";
 for(let attempt=0;attempt<2;attempt++){
   const r=await fetch("https://api.groq.com/openai/v1/chat/completions",{method:"POST",headers:{Authorization:"Bearer "+GROQ_API_KEY,"Content-Type":"application/json","Groq-Model-Version":"latest","User-Agent":"nd-safe-tool-broker/9h"},body:JSON.stringify(payload)});
   const t=await r.text();
   if(r.ok){
     const j=JSON.parse(t),msg=j.choices?.[0]?.message||{},exec=msg.executed_tools||[];
     const names=exec.map(x=>String(x?.type||x?.name||x?.tool_name||"").toLowerCase());
     if(!exec.length||!names.some(x=>x.includes("web_search")||x.includes("search")))throw new Error("web verification used no search tool");
     const urls=[];const blob=JSON.stringify(exec)+" "+String(msg.content||"");
     for(const m of blob.matchAll(/https?:\\/\\/[^\\s\"'<>]+/g)){const u=m[0].replace(/[).,;\\]]+$/,'');if(!urls.includes(u))urls.push(u);if(urls.length>=10)break;}
     if(urls.length<1)throw new Error("web verification returned no source URLs");
     return {brief:String(msg.content||"").trim().slice(0,5000),source_urls:urls,tool_calls:exec.length,verified_search:true,model:"groq/compound-mini",query_chars:query.length,mutations:false};
   }
   last="groq "+r.status+": "+t.slice(0,300);
   if(r.status===429&&attempt===0){await new Promise(res=>setTimeout(res,15000));continue;}
   throw new Error(last);
 }
 throw new Error(last||"web verification failed");
}
`;
src=src.slice(0,start)+fn+src.slice(end);
const loop='for(const [tool,q] of tests){';
if(!src.includes(loop))throw new Error('v9h probe loop missing');
src=src.replace(loop,'for(const [tool,q] of tests){if(tool===\"web_current\")await new Promise(r=>setTimeout(r,65000));');
src=src.replace('ND_SAFE_TOOL_BROKER_V9B_WEB_RESILIENT_START','ND_SAFE_TOOL_BROKER_V9H_WEB_RESILIENT_START');
await Bun.write('/tmp/nd-broker-v9h-inner.js',src);
await import('file:///tmp/nd-broker-v9h-inner.js');
