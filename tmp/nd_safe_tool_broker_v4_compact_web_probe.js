const BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/46de9fcfa1f0c44863e9dd491d480e8e5160aca4/tmp/nd_safe_tool_broker_v2.js';
let src=await (await fetch(BASE)).text();
const start=src.indexOf('async function webCurrent(q){');
const end=src.indexOf('async function invokeTool(name,q){',start);
if(start<0||end<0)throw new Error('webCurrent block not found');
const compact=String.raw`async function webCurrent(q){
  if(!GROQ_API_KEY)throw new Error("groq research unavailable");
  const today=new Date().toISOString().slice(0,10);
  const query=String(q||"").replace(/\s+/g," ").trim().slice(0,1800);
  if(!query)throw new Error("empty web research query");
  const payload={
    model:GROQ_RESEARCH_MODEL,
    messages:[
      {role:"system",content:"Date: "+today+". READ-ONLY current-web verifier. MUST call web_search; visit primary/official pages when useful. Return <=900 words, factual and source-backed. Every current claim needs a direct URL and date when available. If verification fails, say unavailable; never answer from model memory."},
      {role:"user",content:query}
    ],
    max_completion_tokens:1200,
    compound_custom:{tools:{enabled_tools:["web_search","visit_website"]}}
  };
  async function callOnce(){
    const r=await fetch("https://api.groq.com/openai/v1/chat/completions",{method:"POST",headers:{Authorization:"Bearer "+GROQ_API_KEY,"Content-Type":"application/json","Groq-Model-Version":"latest","User-Agent":"nd-safe-tool-broker/4.0"},body:JSON.stringify(payload)});
    const t=await r.text();return {r,t};
  }
  let {r,t}=await callOnce();
  if(r.status===429){await new Promise(res=>setTimeout(res,1200));({r,t}=await callOnce());}
  if(!r.ok)throw new Error("groq "+r.status+": "+t.slice(0,350));
  const j=JSON.parse(t),msg=j.choices?.[0]?.message||{},exec=msg.executed_tools||[];
  const names=exec.map(x=>String(x?.type||x?.name||x?.tool_name||"").toLowerCase());
  if(!exec.length||!names.some(x=>x.includes("web_search")||x.includes("search")))throw new Error("web verification used no search tool");
  const urls=[];const raw=JSON.stringify(exec)+" "+String(msg.content||"");
  for(const m of raw.matchAll(/https?:\/\/[^\s"'<>]+/g)){const u=m[0].replace(/[).,;\]]+$/,"");if(!urls.includes(u))urls.push(u);if(urls.length>=10)break;}
  if(!urls.length)throw new Error("web verification returned no source URLs");
  return {brief:String(msg.content||"").trim().slice(0,6500),source_urls:urls,tool_calls:exec.length,verified_search:true,query_chars:query.length,mutations:false};
}
`;
src=src.slice(0,start)+compact+src.slice(end);
const needle='Bun.serve({port:PORT,fetch:handler});';
if(!src.includes(needle))throw new Error('serve marker not found');
const probe=String.raw`setTimeout(async()=>{
  try{
    const r=await webCurrent("Find the latest official OpenAI ChatGPT release-notes update. Use official OpenAI source only. Return the direct URL and publication/update date.");
    console.log("WEB_CURRENT_PROBE",JSON.stringify({ok:true,verified_search:r.verified_search,tool_calls:r.tool_calls,source_count:(r.source_urls||[]).length,first_source:(r.source_urls||[])[0]||null,brief_chars:(r.brief||"").length,mutations:false}));
  }catch(e){console.error("WEB_CURRENT_PROBE",JSON.stringify({ok:false,error:String(e).slice(0,500),mutations:false}));}
},1800);
`;
src=src.replace(needle,probe+'\n'+needle);
await import('data:text/javascript;base64,'+Buffer.from(src).toString('base64'));
