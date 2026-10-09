// Synthetic/metadata-only audit of existing free route and provider env presence. No user messages or credentials logged.
async function audit(){
 const flags={zai:Boolean(process.env.ZAI_API_KEY),cerebras:Boolean(process.env.CEREBRAS_API_KEY),mistral:Boolean(process.env.MISTRAL_API_KEY),openrouter:Boolean(process.env.OPENROUTER_API_KEY)};
 console.log("ND_PROVIDER_PARENT_ENV_PRESENCE",JSON.stringify(flags));
 if(!flags.openrouter)return;
 const hdr={Authorization:"Bearer "+process.env.OPENROUTER_API_KEY};
 for(const [name,url] of [['zdr','https://openrouter.ai/api/v1/endpoints/zdr'],['models_zdr','https://openrouter.ai/api/v1/models?zdr=true']]){
  try{
   const r=await fetch(url,{headers:hdr,signal:AbortSignal.timeout(12000)});
   const obj=await r.json().catch(()=>({}));
   const arr=Array.isArray(obj.data)?obj.data:[];
   const free=arr.filter(x=>{
    const id=String(x.model_id||x.id||"");
    const p=x.pricing||{};
    return id.endsWith(":free")||((p.prompt==="0"||p.prompt===0)&&(p.completion==="0"||p.completion===0));
   }).map(x=>String(x.model_id||x.id||""));
   console.log("ND_OPENROUTER_ZDR_INVENTORY",JSON.stringify({source:name,http:r.status,total:arr.length,free_models:free.slice(0,45),count:free.length}));
  }catch(e){console.log("ND_OPENROUTER_ZDR_INVENTORY",JSON.stringify({source:name,error_type:String(e?.name||"Error")}))}
 }
}
setTimeout(()=>void audit(),6500).unref();