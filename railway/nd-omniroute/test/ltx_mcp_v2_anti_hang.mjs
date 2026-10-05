process.env.KAGGLE_API_TOKEN='test-token';
process.env.KAGGLE_USERNAME_SLUG='testuser';
process.env.ND_LTX_MCP_PATH_TOKEN='stable-result-test-token';
process.env.ND_LTX_STATUS_CONTROL_TIMEOUT_MS='80';
process.env.ND_LTX_SUBMIT_CONTROL_TIMEOUT_MS='100';
process.env.ND_LTX_RECONCILE_CONTROL_TIMEOUT_MS='120';
process.env.ND_LTX_RESULT_CONTROL_TIMEOUT_MS='120';
process.env.ND_LTX_INPUT_TOKEN='test-input-token';
process.env.ND_LTX_INPUT_BASE='https://bridge.example';

const {createLtxMcpHandler,ltxHealth}=await import('../ltx_mcp_v2.mjs?nam397-test');

const json=o=>new Response(JSON.stringify(o),{status:200,headers:{'content-type':'application/json'}});
function hanging(signal,onAbort=()=>{}){
  const stream=new ReadableStream({start(controller){
    signal?.addEventListener('abort',()=>{onAbort();try{controller.error(signal.reason||new Error('aborted'));}catch{}},{once:true});
  },cancel(){onAbort();}});
  return new Response(stream,{status:200,headers:{'content-type':'application/json'}});
}
async function call(name,args={}){
  const handler=createLtxMcpHandler();
  const body=Buffer.from(JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/call',params:{name,arguments:args}}));
  const req={method:'POST',async *[Symbol.asyncIterator](){yield body;}};
  let out=Buffer.alloc(0);
  const res={writeHead(){},end(data){if(data)out=Buffer.concat([out,Buffer.isBuffer(data)?data:Buffer.from(data)]);}};
  await handler(req,res);
  return JSON.parse(out.toString('utf8')).result;
}
async function list(){
  const handler=createLtxMcpHandler();
  const body=Buffer.from(JSON.stringify({jsonrpc:'2.0',id:2,method:'tools/list',params:{}}));
  const req={method:'POST',async *[Symbol.asyncIterator](){yield body;}};
  let out=Buffer.alloc(0);
  const res={writeHead(){},end(data){if(data)out=Buffer.concat([out,Buffer.isBuffer(data)?data:Buffer.from(data)]);}};
  await handler(req,res);
  return JSON.parse(out.toString('utf8')).result;
}

{
  const names=(await list()).tools.map(x=>x.name);
  const expected=['ltx_generate_keyframes','ltx_keyframe_reconcile','ltx_keyframe_status','ltx_keyframe_result'];
  if(JSON.stringify(names)!==JSON.stringify(expected))throw new Error('surface mismatch '+JSON.stringify(names));
  const h=await ltxHealth();
  if(h.runtime_profile!=='DURABLE_ASYNC'||h.control_contract?.ambiguous_submit!=='RECONCILE_SAME_EFFECT_BEFORE_RESUBMIT')throw new Error('health contract missing');
  console.log('PRIMARY_V2_SURFACE=PASS');
}

{
  let cancelled=false;
  globalThis.fetch=async (url,opts={})=>{
    const u=String(url);
    if(u.includes('/security.OAuthService/IntrospectToken'))return json({active:true,username:'testuser'});
    if(u.includes('/kernels.KernelsApiService/GetKernelSessionStatus'))return hanging(opts.signal,()=>{cancelled=true;});
    throw new Error('unexpected '+u);
  };
  const t=Date.now();
  const envelope=await call('ltx_keyframe_status',{request_id:'k2b-r123456789abc-def0-v1'});
  const elapsed=Date.now()-t;
  const out=envelope.structuredContent;
  if(out?.state!=='CONTROL_DEADLINE'||out?.error_code!=='CONTROL_DEADLINE')throw new Error('deadline contract '+JSON.stringify(out));
  if(elapsed>500||!cancelled)throw new Error('managed I/O not aborted '+elapsed);
  console.log('PRIMARY_V2_HANGING_BODY=PASS',elapsed);
}

{
  const effectId='ltx2b:'+'a'.repeat(64);
  let kernels=[];
  globalThis.fetch=async (url,opts={})=>{
    const u=String(url),body=opts.body?JSON.parse(String(opts.body)):{};
    if(u.includes('/security.OAuthService/IntrospectToken'))return json({active:true,username:'testuser'});
    if(u.includes('/kernels.KernelsApiService/ListKernels')){
      const search=String(body.search||'').toLowerCase();
      return json({kernels:kernels.filter(k=>String(k.slug).toLowerCase().includes(search))});
    }
    if(u.includes('/kernels.KernelsApiService/GetKernelSessionStatus'))return json({status:1});
    throw new Error('unexpected '+u);
  };
  const unknown=(await call('ltx_keyframe_reconcile',{effect_id:effectId})).structuredContent;
  if(unknown?.state!=='OUTCOME_UNKNOWN'||unknown?.safe_to_resubmit!==false)throw new Error('unsafe negative reconcile '+JSON.stringify(unknown));
  kernels=[{slug:'nd-ltx2b-'+unknown.effect_token,ref:'testuser/nd-ltx2b-'+unknown.effect_token,author:'testuser',currentVersionNumber:1}];
  const recovered=(await call('ltx_keyframe_reconcile',{effect_id:effectId})).structuredContent;
  if(recovered?.state!=='RUNNING'||!recovered?.request_id)throw new Error('reconcile failed '+JSON.stringify(recovered));
  console.log('PRIMARY_V2_RECONCILE=PASS',recovered.request_id);
}

{
  let outputCalls=0,listOutputCalls=0;
  globalThis.fetch=async (url,opts={})=>{
    const u=String(url),body=opts.body?JSON.parse(String(opts.body)):{};
    if(u.includes('/security.OAuthService/IntrospectToken'))return json({active:true,username:'testuser'});
    if(u.includes('/kernels.KernelsApiService/GetKernelSessionStatus'))return json({status:2});
    if(u.includes('/kernels.KernelsApiService/ListKernelSessionOutput')){listOutputCalls++;return json({files:[]});}
    if(u.includes('/kernels.KernelsApiService/DownloadKernelOutput')){outputCalls++;return new Response(null,{status:302,headers:{location:'https://provider.invalid/'+String(body.filePath||'result.bin')+'?fresh=1'}});}
    throw new Error('unexpected '+u);
  };
  const ready=(await call('ltx_keyframe_result',{request_id:'k2b-r123456789abc-def0-v1'})).structuredContent;
  if(ready?.state!=='READY'||ready?.result_mode!=='PROVIDER_REFERENCE')throw new Error('bounded result failed '+JSON.stringify(ready));
  if(!String(ready?.stable_video_url||'').includes('/ltx-result/stable-result-test-token/'+ready.request_id+'.mp4'))throw new Error('stable video reference missing '+JSON.stringify(ready));
  if(listOutputCalls!==0||outputCalls<1||outputCalls>2)throw new Error('result pagination/regression');
  console.log('PRIMARY_V2_BOUNDED_RESULT=PASS');
}

{
  const visited=[];
  globalThis.fetch=async (url,opts={})=>{
    const u=String(url); visited.push(u);
    const body=opts.body?JSON.parse(String(opts.body)):{};
    if(u.startsWith('https://bridge.example/ltx-input/')){
      return new Response(Buffer.from('fake-image-bytes'),{status:200,headers:{'content-type':'image/jpeg','content-length':'16'}});
    }
    if(u.includes('/security.OAuthService/IntrospectToken'))return json({active:true,username:'testuser'});
    if(u.includes('/kernels.KernelsApiService/ListKernels'))return json({kernels:[]});
    if(u.includes('/kernels.KernelsApiService/GetAcceleratorQuotaStatistics'))return json({gpuQuota:{timeUsed:'0s',timeReserved:'0s',totalTimeAllowed:'108000s'}});
    if(u.includes('/kernels.KernelsApiService/SaveKernel'))return json({versionNumber:1});
    throw new Error('unexpected '+u);
  };
  const out=(await call('ltx_generate_keyframes',{
    start_image_url:'drive:ABCDEFGHIJKL12345',
    end_image_url:'drive:ZYXWVUTSRQP098765',
    prompt:'bridge fixture',duration_seconds:2,width:512,height:288,seed:7,idempotency_key:'bridge-fixture'
  })).structuredContent;
  if(out?.state!=='SUBMITTED')throw new Error('bridge submit failed '+JSON.stringify(out));
  if(visited.some(x=>x.includes('127.0.0.1')))throw new Error('localhost bridge regression');
  if(visited.filter(x=>x.startsWith('https://bridge.example/ltx-input/')).length!==2)throw new Error('external bridge not used twice');
  console.log('PRIMARY_V2_EXTERNAL_INPUT_BRIDGE=PASS');
}


{
  let kernels=[],saveCalls=0,nextVersion=1,providerStatus=1;
  globalThis.fetch=async (url,opts={})=>{
    const u=String(url),body=opts.body?JSON.parse(String(opts.body)):{};
    if(u.includes('/security.OAuthService/IntrospectToken'))return json({active:true,username:'testuser'});
    if(u.includes('/kernels.KernelsApiService/ListKernels')){
      const search=String(body.search||'').toLowerCase();
      return json({kernels:kernels.filter(k=>String(k.slug).toLowerCase().includes(search))});
    }
    if(u.includes('/kernels.KernelsApiService/GetAcceleratorQuotaStatistics'))return json({gpuQuota:{timeUsed:'0s',timeReserved:'0s',totalTimeAllowed:'108000s'}});
    if(u.includes('/kernels.KernelsApiService/GetKernelSessionStatus'))return json({status:providerStatus});
    if(u.includes('/kernels.KernelsApiService/SaveKernel')){
      saveCalls++;
      const slug=String(body.slug).split('/').pop(),version=nextVersion++;
      kernels=[{slug,ref:'testuser/'+slug,author:'testuser',currentVersionNumber:version}];
      return json({versionNumber:version});
    }
    throw new Error('unexpected '+u);
  };
  const args={start_image_url:'https://example.org/a.jpg',end_image_url:'https://example.org/b.jpg',prompt:'terminal retry',duration_seconds:2,width:512,height:288,seed:99,idempotency_key:'primary-terminal-retry'};
  const first=(await call('ltx_generate_keyframes',args)).structuredContent;
  if(first?.state!=='SUBMITTED'||saveCalls!==1)throw new Error('primary terminal retry initial submit failed '+JSON.stringify(first));
  providerStatus=4;
  const blocked=(await call('ltx_generate_keyframes',args)).structuredContent;
  if(blocked?.state!=='CANCELLED'||blocked?.reused_existing!==true||saveCalls!==1)throw new Error('primary ordinary repeat was not blocked '+JSON.stringify(blocked));
  const retried=(await call('ltx_generate_keyframes',{...args,retry_terminal:true})).structuredContent;
  if(retried?.state!=='SUBMITTED'||saveCalls!==2)throw new Error('primary explicit terminal retry failed '+JSON.stringify(retried));
  if(retried?.effect_id!==first?.effect_id||retried?.request_id===first?.request_id)throw new Error('primary retry identity/version mismatch');
  console.log('PRIMARY_V2_TERMINAL_RETRY=PASS',first.request_id,'->',retried.request_id);
}

console.log('ND_LTX_PRIMARY_V2_ANTI_HANG=PASS');
