export const LTX_CONTROL_DEFAULT_MS={submit:30000,status:20000,result:25000,reconcile:20000,download:60000};
export const LTX_CONTROL_TEXT_MAX_BYTES=2*1024*1024;
export const LTX_CONTROL_INPUT_MAX_BYTES=20*1024*1024;

export function ltxControlTimeout(kind,env=process.env){
  const envKey='ND_LTX_'+String(kind).toUpperCase()+'_CONTROL_TIMEOUT_MS';
  const n=Number(env?.[envKey]);
  return Number.isFinite(n)&&n>0?Math.max(250,Math.floor(n)):(LTX_CONTROL_DEFAULT_MS[kind]||20000);
}

export function ltxControlDeadlineError(label,timeoutMs){
  const e=new Error('CONTROL_DEADLINE: '+label+' exceeded '+timeoutMs+'ms');
  e.code='CONTROL_DEADLINE';
  e.status=408;
  e.timeout_ms=timeoutMs;
  e.outcome_state='OUTCOME_UNKNOWN';
  return e;
}

export function makeLtxControlContext(label,timeoutMs){
  const controller=new AbortController();
  const deadlineAt=Date.now()+timeoutMs;
  let deadlineTriggered=false;
  const timer=setTimeout(()=>{
    deadlineTriggered=true;
    try{controller.abort(ltxControlDeadlineError(label,timeoutMs));}catch{}
  },timeoutMs);
  return {
    label,timeoutMs,deadlineAt,signal:controller.signal,
    isDeadline(){return deadlineTriggered||Date.now()>=deadlineAt;},
    remainingMs(){return Math.max(0,deadlineAt-Date.now());},
    throwIfExpired(){if(this.isDeadline()) throw ltxControlDeadlineError(label,timeoutMs);},
    abort(reason){if(!controller.signal.aborted){try{controller.abort(reason);}catch{}}},
    close(){clearTimeout(timer);}
  };
}

export async function withLtxControlDeadline(label,timeoutMs,fn){
  const ctx=makeLtxControlContext(label,timeoutMs);
  try{return await fn(ctx);}
  catch(e){
    if(ctx.isDeadline()) throw ltxControlDeadlineError(label,timeoutMs);
    ctx.abort(e);
    throw e;
  }finally{ctx.close();}
}

export async function ltxFetch(url,opts={},ctx){
  ctx?.throwIfExpired();
  try{return await fetch(url,{...opts,signal:ctx?.signal});}
  catch(e){
    if(ctx?.isDeadline()) throw ltxControlDeadlineError(ctx.label,ctx.timeoutMs);
    throw e;
  }
}

export async function ltxReadBoundedBytes(res,ctx,maxBytes,label='response'){
  const cap=Math.max(1,Number(maxBytes)||1);
  const declared=Number(res.headers.get('content-length')||0);
  if(declared>cap) throw Object.assign(new Error(label+' exceeds '+cap+' bytes'),{code:'BODY_TOO_LARGE',status:413});
  if(!res.body?.getReader){
    const buf=Buffer.from(await res.arrayBuffer());
    if(ctx?.isDeadline()) throw ltxControlDeadlineError(ctx.label,ctx.timeoutMs);
    if(buf.length>cap) throw Object.assign(new Error(label+' exceeds '+cap+' bytes'),{code:'BODY_TOO_LARGE',status:413});
    return buf;
  }
  const reader=res.body.getReader();
  const chunks=[]; let total=0;
  const onAbort=()=>{try{reader.cancel(ctx?.signal?.reason||'aborted').catch(()=>{});}catch{}};
  if(ctx?.signal) ctx.signal.addEventListener('abort',onAbort,{once:true});
  try{
    while(true){
      ctx?.throwIfExpired();
      const part=await reader.read();
      if(ctx?.isDeadline()) throw ltxControlDeadlineError(ctx.label,ctx.timeoutMs);
      if(part.done) break;
      const b=Buffer.from(part.value); total+=b.length;
      if(total>cap){
        try{await reader.cancel('body_limit');}catch{}
        throw Object.assign(new Error(label+' exceeds '+cap+' bytes'),{code:'BODY_TOO_LARGE',status:413});
      }
      chunks.push(b);
    }
    return Buffer.concat(chunks,total);
  }finally{
    if(ctx?.signal) ctx.signal.removeEventListener('abort',onAbort);
  }
}

export async function ltxReadBoundedText(res,ctx,maxBytes=LTX_CONTROL_TEXT_MAX_BYTES,label='response'){
  return (await ltxReadBoundedBytes(res,ctx,maxBytes,label)).toString('utf8');
}
