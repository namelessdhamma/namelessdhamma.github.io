// Privacy-gated Russian qualification. Synthetic query, no actual VK content.
async function run(){
 const key=String(process.env.OPENROUTER_API_KEY||'').trim();
 if(!key)return console.log('ND_OPENROUTER_PRIVACY_QA',JSON.stringify({result:'no_key'}));
 const model='nvidia/nemotron-3-super-120b-a12b:free';
 const candidate_modes=[
  {data_collection:'deny',zdr:true},
  {data_collection:'deny'}
 ];
 for(let i=0;i<candidate_modes.length;i++){
  const result={candidate:model,mode:i===0?'deny_and_zdr':'deny_only',model_is_free:true};
  try{
   const resp=await fetch('https://openrouter.ai/api/v1/chat/completions',{method:'POST',headers:{Authorization:'Bearer '+key,'Content-Type':'application/json','HTTP-Referer':'https://namelessdhamma.org'},
    body:JSON.stringify({model,provider:candidate_modes[i],messages:[{role:'system',content:'Отвечай коротко на русском языке.'},{role:'user',content:'Одно короткое русское предложение о падающем снеге.'}],max_tokens:450,temperature:0.1}),signal:AbortSignal.timeout(30000)});
   const doc=await resp.json().catch(()=>({}));
   const answer=String(doc?.choices?.[0]?.message?.content||'');
   result.status=resp.status;result.russian=/[А-Яа-яЁё]/.test(answer);result.nonempty=answer.trim().length>0;
   if(!resp.ok){result.error_code=doc?.error?.code||null;result.error_type=doc?.error?.type||null}
  }catch(e){result.error_type=String(e?.name||'Error').slice(0,40)}
  console.log('ND_OPENROUTER_PRIVACY_QA',JSON.stringify(result));
  if(result.status===200&&result.russian&&result.nonempty)break;
 }
}
setTimeout(()=>void run(),9000).unref();