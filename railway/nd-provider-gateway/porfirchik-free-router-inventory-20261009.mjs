// Synthetic Russian evaluation of no-charge, no-retention, no-data-collection OpenRouter endpoint. Never log prompt or content.
async function probe(){
 const key=String(process.env.OPENROUTER_API_KEY||"");if(!key)return;
 const model="inclusionai/ling-3.1-flash";
 const hdr={Authorization:"Bearer "+key,"Content-Type":"application/json","HTTP-Referer":"https://namelessdhamma.org"};
 const prompts=["Ответь ровно одним русским предложением: как отличить облако от тумана?","Дай короткий ответ на русском языке: зачем сохранять запись после перезапуска сервера?"];
 for(let i=0;i<prompts.length;i++){
  let out={model,attempt:i+1,private_routing:true,max_usd_per_million_tokens:0};
  try{
   const r=await fetch("https://openrouter.ai/api/v1/chat/completions",{method:"POST",headers:hdr,
    body:JSON.stringify({model,provider:{zdr:true,data_collection:"deny",max_price:{prompt:0,completion:0}},messages:[{role:"system",content:"Ты русскоязычный помощник. Дай ясный ответ без внутренних рассуждений."},{role:"user",content:prompts[i]}],max_tokens:500,temperature:0.15}),signal:AbortSignal.timeout(28000)});
   const j=await r.json().catch(()=>({}));
   const answer=String(j?.choices?.[0]?.message?.content||"");
   out.http=r.status;out.cyrillic=/[А-Яа-яЁё]/.test(answer);out.has_answer=Boolean(answer.trim());out.length=answer.length;
   if(!r.ok)out.error_code=j?.error?.code||null;
  }catch(e){out.error_type=String(e?.name||"Error").slice(0,48)}
  console.log("ND_STRICT_PRIVACY_FREE_ROUTER_QA",JSON.stringify(out));
  if(out.http!==200||!out.cyrillic)break;
 }
}
setTimeout(()=>void probe(),7000).unref();