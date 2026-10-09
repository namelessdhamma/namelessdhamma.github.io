// Temporary synthetic-only OpenRouter free-model qualification. No VK or personal data.
const candidates=['nvidia/nemotron-3-ultra-550b-a55b:free','nvidia/nemotron-3-super-120b-a12b:free'];
async function qualify(){
 const key=String(process.env.OPENROUTER_API_KEY||'').trim();
 if(!key)return console.log('ND_OPENROUTER_NEW_FREE_QA',JSON.stringify({phase:'SKIP',reason:'no_key'}));
 for(const model of candidates){
  const detail={model,synthetic:true,zero_price_model_slug:model.endsWith(':free')};
  try{
   const response=await fetch('https://openrouter.ai/api/v1/chat/completions',{
    method:'POST',headers:{'Authorization':'Bearer '+key,'Content-Type':'application/json','HTTP-Referer':'https://namelessdhamma.org','X-Title':'ND Porfirchik synthetic Russian route qualification'},
    body:JSON.stringify({model,messages:[{role:'system',content:'Отвечай на русском языке. Только окончательный ответ, без рассуждений.'},{role:'user',content:'Напиши одно короткое предложение на русском языке о погоде, не упоминая никаких людей.'}],max_tokens:450,temperature:0.15}),signal:AbortSignal.timeout(35000)});
   let body=await response.json().catch(()=>({}));
   const answer=String(body?.choices?.[0]?.message?.content||'');
   detail.http=response.status;detail.valid_russian_answer=response.ok&&/[А-Яа-яЁё]/.test(answer);detail.has_content=Boolean(answer.trim());
   if(!response.ok){detail.error_code=body?.error?.code||null;detail.error_type=body?.error?.type||null}
  }catch(e){detail.error_type=String(e?.name||'Error').slice(0,45)}
  console.log('ND_OPENROUTER_NEW_FREE_QA',JSON.stringify(detail));
 }
}
setTimeout(()=>{void qualify();},9000).unref();