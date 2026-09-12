console.log('ND_SAFE_TOOL_BROKER_V10_GLM_WRAPPER_START');

const BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/1c01b3551cdce1997c46aa81dd2ae4c72a551b72/tmp/nd_safe_tool_broker_v9b_web_resilient.js';
let src=await (await fetch(BASE)).text();

const citation=',citation_options:"enabled"';
if(!src.includes(citation)) throw new Error('v10 citation marker missing');
src=src.replace(citation,'');

const waitOld='r.status===429?1500:800';
if(!src.includes(waitOld)) throw new Error('v10 retry marker missing');
src=src.replace(waitOld,'r.status===429?12000:800');

const payloadOld='const payload={model:plan.model,messages:[{role:"user",content:plan.query}]};';
if(!src.includes(payloadOld)) throw new Error('v10 payload marker missing');
src=src.replace(payloadOld,'const payload={model:plan.model,messages:[{role:"user",content:plan.query}],max_completion_tokens:1200};');

src=src.replace('ND_SAFE_TOOL_BROKER_V9B_WEB_RESILIENT_START','ND_SAFE_TOOL_BROKER_V10_GLM_START');

const finalMarker="const encoded=Buffer.from(patched).toString('base64');";
if(!src.includes(finalMarker)) throw new Error('v10 final-runtime marker missing');

const glmPatch = String.raw`
const glmEnvMarker='const GROQ_RESEARCH_MODEL = process.env.GROQ_RESEARCH_MODEL || "groq/compound";';
if(!patched.includes(glmEnvMarker))throw new Error("glm env marker missing");
patched=patched.replace(glmEnvMarker,glmEnvMarker+'\nconst ZAI_API_KEY = process.env.ZAI_API_KEY || "";\nconst ZAI_MODEL = process.env.ZAI_MODEL || "glm-5.3-flash";\nconst ZAI_BASE_URL = (process.env.ZAI_BASE_URL || "https://api.z.ai/api/paas/v4").replace(/\\\/$/,"");');

const glmCatalogMarker='{name:"web_current",description:"Current web research through Groq Compound web-search/website tools."},';
if(!patched.includes(glmCatalogMarker))throw new Error("glm catalog marker missing");
patched=patched.replace(glmCatalogMarker,glmCatalogMarker+'\n    {name:"external_ai",description:"Bounded advisory call to external auxiliary intelligence (Z.AI GLM). No tools, no write authority, no provider/model override."},');

const glmInvokeMarker='async function invokeTool(name,q,args={}){';
if(!patched.includes(glmInvokeMarker))throw new Error("glm invoke marker missing");
const glmFn=String.raw\`
function redactExternal(s){
  return String(s||"")
    .replace(/-----BEGIN [^-]*PRIVATE KEY-----[\\s\\S]*?-----END [^-]*PRIVATE KEY-----/gi,"[REDACTED_PRIVATE_KEY]")
    .replace(/\\b(sk-[A-Za-z0-9_-]{16,})\\b/g,"[REDACTED_KEY]")
    .replace(/\\b(gh[pousr]_[A-Za-z0-9]{20,})\\b/g,"[REDACTED_GITHUB_TOKEN]")
    .replace(/((?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|private[_-]?key)\\s*[:=]\\s*)[^\\s,"'}]+/gi,"$1[REDACTED]");
}
async function externalAI(q,args={}){
  if(!ZAI_API_KEY)throw new Error("zai external ai unavailable");
  const role=String(args?.role||"critic");
  const roles={
    critic:"You are an independent auxiliary critic for Nameless Dhamma. Find concrete weaknesses, hidden assumptions, likely failures, and better alternatives. Be concise and evidence-oriented. You are advisory only and have no authority or tool access.",
    reviewer:"You are an independent software reviewer for Nameless Dhamma. Inspect supplied code or diff for correctness, security, reliability, maintainability, edge cases, and missing tests. Prioritize actionable defects over style commentary. You are advisory only and have no authority or tool access.",
    coder:"You are an auxiliary coding model for Nameless Dhamma. Produce the smallest correct implementation or patch that satisfies the request. State assumptions and include tests when useful. Do not invent access to tools or secrets. Your output is a proposal that must be verified by the controlling GPT/True Developer.",
    agent_planner:"You are an independent agent-plan critic for Nameless Dhamma. Evaluate the proposed plan for unsafe authority expansion, missing failure handling, unnecessary complexity, cost, resumability, and verification gaps. Return bounded recommendations only; you have no authority or tool access."
  };
  if(!roles[role])throw new Error("external ai role denied");
  const task=redactExternal(String(q||"").slice(0,12000)).trim();
  if(!task)throw new Error("external ai empty task");
  const context=redactExternal(String(args?.context||"").slice(0,30000));
  const content=context?("CONTEXT:\\n"+context+"\\n\\nTASK:\\n"+task):task;
  const mt=Math.min(Math.max(Number(args?.max_tokens||4096)||4096,256),8192);
  const temp=Math.min(Math.max(Number(args?.temperature??0.2)||0,0),1.5);
  const payload={
    model:ZAI_MODEL,
    messages:[
      {role:"system",content:roles[role]},
      {role:"user",content}
    ],
    stream:false,
    max_tokens:mt,
    temperature:temp,
    thinking:{type:args?.thinking===false?"disabled":"enabled"}
  };
  let last="";
  for(let attempt=0;attempt<3;attempt++){
    let r,t;
    try{
      r=await fetch(ZAI_BASE_URL+"/chat/completions",{
        method:"POST",
        headers:{
          Authorization:"Bearer "+ZAI_API_KEY,
          "Content-Type":"application/json",
          "Accept-Language":"en-US,en",
          "User-Agent":"nd-safe-tool-broker/10-glm"
        },
        body:JSON.stringify(payload)
      });
      t=await r.text();
    }catch(e){
      last="zai network: "+String(e).slice(0,220);
      if(attempt<2){await new Promise(res=>setTimeout(res,1200*(attempt+1)));continue;}
      break;
    }
    if(r.ok){
      const j=JSON.parse(t),choice=j.choices?.[0]||{},msg=choice.message||{};
      return {
        provider:"zai",
        model:j.model||ZAI_MODEL,
        role,
        content:String(msg.content||""),
        reasoning_content:msg.reasoning_content||null,
        finish_reason:choice.finish_reason||null,
        usage:j.usage||{},
        authority:"ADVISORY_ONLY",
        tool_access:false,
        mutations:false
      };
    }
    last="zai "+r.status+": "+t.slice(0,300);
    if((r.status===429||r.status>=500)&&attempt<2){await new Promise(res=>setTimeout(res,1500*(2**attempt)));continue;}
    break;
  }
  throw new Error(last||"zai external ai failed");
}
\`;
patched=patched.replace(glmInvokeMarker,glmFn+'\n'+glmInvokeMarker+'if(name==="external_ai")return await externalAI(q,args);');

const glmStartOld='console.log("ND_SAFE_TOOL_BROKER_V9B_WEB_RESILIENT_START",JSON.stringify({port:PORT,statehead_id:STATEHEAD_ID,google:!!CLIENT_EMAIL&&!!PRIVATE_KEY_B64,github:!!GITHUB_TOKEN,web:!!GROQ_API_KEY,canonical_mutations:false,sandbox_mutations:true,father_root:FATHER_ROOT_ID,storage:"OWNER_OWNED_DRIVE_COMMENT_APPEND_ONLY_LEDGERS"}));';
if(patched.includes(glmStartOld)){
  patched=patched.replace(glmStartOld,'console.log("ND_SAFE_TOOL_BROKER_V10_GLM_START",JSON.stringify({port:PORT,statehead_id:STATEHEAD_ID,google:!!CLIENT_EMAIL&&!!PRIVATE_KEY_B64,github:!!GITHUB_TOKEN,web:!!GROQ_API_KEY,zai_external_ai:!!ZAI_API_KEY,canonical_mutations:false,sandbox_mutations:true,father_root:FATHER_ROOT_ID,storage:"OWNER_OWNED_DRIVE_COMMENT_APPEND_ONLY_LEDGERS"}));');
}
`;

src=src.replace(finalMarker,glmPatch+'\n'+finalMarker);

await Bun.write('/tmp/nd-broker-v10-glm-inner.js',src);
await import('file:///tmp/nd-broker-v10-glm-inner.js');
