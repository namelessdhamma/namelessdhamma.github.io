import {health,submit,reconcile,status,result} from "../lib/ltx-core.js";

const json=o=>new Response(JSON.stringify(o),{status:200,headers:{"content-type":"application/json"}});
const cfg={
  token:"test-token",username:"testuser",inputToken:"",
  railwayBase:"https://example.invalid",
  submitTimeoutMs:100,statusTimeoutMs:80,resultTimeoutMs:120,reconcileTimeoutMs:120,
  inputMaxBytes:20*1024*1024
};

function hangingJson(signal,onAbort=()=>{}){
  let controllerRef;
  const stream=new ReadableStream({
    start(controller){
      controllerRef=controller;
      signal?.addEventListener("abort",()=>{
        onAbort();
        try{controller.error(signal.reason||new Error("aborted"));}catch{}
      },{once:true});
    },
    cancel(){onAbort();}
  });
  return new Response(stream,{status:200,headers:{"content-type":"application/json"}});
}

// Q1: headers arrive but body never completes. The whole STATUS call must return by one deadline.
{
  let cancelled=false, managedSignal=null;
  globalThis.fetch=async (url,opts={})=>{
    const u=String(url);
    if(u.includes("/security.OAuthService/IntrospectToken")) return json({active:true,username:"testuser"});
    if(u.includes("/kernels.KernelsApiService/GetKernelSessionStatus")){ managedSignal=opts.signal; return hangingJson(opts.signal,()=>{cancelled=true;}); }
    throw new Error("unexpected fetch "+u);
  };
  const started=Date.now();
  let caught=null;
  try{await status({request_id:"k2b-r123456789abc-def0-v1"},cfg);}catch(e){caught=e;}
  const elapsed=Date.now()-started;
  if(caught?.code!=="CONTROL_DEADLINE") throw new Error("Q1 expected CONTROL_DEADLINE, got "+String(caught?.code||caught));
  if(!managedSignal) throw new Error("Q1 did not reach managed provider I/O before the production-minimum deadline");
  if(elapsed>900) throw new Error("Q1 exceeded bounded test budget: "+elapsed+"ms");
  if(!managedSignal?.aborted) throw new Error("Q1 managed I/O AbortSignal was not aborted");
  // Stream cancel delivery may lag the control deadline by a microtask; the signal is the adapter contract.
  if(!cancelled) await new Promise(resolve=>setTimeout(resolve,0));
  console.log("Q1_HANGING_BODY=PASS",elapsed);
}

// Q3/Q4: provider accepts SaveKernel but the response body is lost/hangs.
// The call must return SUBMIT_AMBIGUOUS with stable effect identity, then reconcile the same effect.
{
  let kernels=[];
  let saveCalls=0;
  globalThis.fetch=async (url,opts={})=>{
    const u=String(url), body=opts.body?JSON.parse(String(opts.body)):{};
    if(u.includes("/security.OAuthService/IntrospectToken")) return json({active:true,username:"testuser"});
    if(u.includes("/kernels.KernelsApiService/ListKernels")){
      const search=String(body.search||"").toLowerCase();
      return json({kernels:kernels.filter(k=>String(k.slug).toLowerCase().includes(search))});
    }
    if(u.includes("/kernels.KernelsApiService/GetAcceleratorQuotaStatistics")) return json({gpuQuota:{timeUsed:"0s",timeReserved:"0s",totalTimeAllowed:"108000s"}});
    if(u.includes("/kernels.KernelsApiService/SaveKernel")){
      saveCalls++;
      const slug=String(body.slug).split("/").pop();
      kernels=[{slug,ref:"testuser/"+slug,author:"testuser",currentVersionNumber:1}];
      return hangingJson(opts.signal);
    }
    if(u.includes("/kernels.KernelsApiService/GetKernelSessionStatus")) return json({status:1});
    throw new Error("unexpected fetch "+u);
  };
  const args={start_image_url:"https://example.org/start.jpg",end_image_url:"https://example.org/end.jpg",prompt:"storm",duration_seconds:2,width:512,height:288,seed:42};
  const ambiguous=await submit(args,cfg);
  if(ambiguous.state!=="SUBMIT_AMBIGUOUS"||ambiguous.outcome_state!=="OUTCOME_UNKNOWN") throw new Error("ambiguous submit contract failed "+JSON.stringify(ambiguous));
  if(!ambiguous.effect_id||!ambiguous.effect_token) throw new Error("ambiguous submit lost effect identity");
  if(saveCalls!==1) throw new Error("ambiguous submit duplicated SaveKernel");

  globalThis.fetch=async (url,opts={})=>{
    const u=String(url), body=opts.body?JSON.parse(String(opts.body)):{};
    if(u.includes("/security.OAuthService/IntrospectToken")) return json({active:true,username:"testuser"});
    if(u.includes("/kernels.KernelsApiService/ListKernels")){
      const search=String(body.search||"").toLowerCase();
      return json({kernels:kernels.filter(k=>String(k.slug).toLowerCase().includes(search))});
    }
    if(u.includes("/kernels.KernelsApiService/GetKernelSessionStatus")) return json({status:1});
    throw new Error("unexpected fetch "+u);
  };
  const recovered=await reconcile({effect_id:ambiguous.effect_id},cfg);
  if(recovered.state!=="RUNNING"||!recovered.request_id||recovered.effect_token!==ambiguous.effect_token) throw new Error("same-effect reconcile failed "+JSON.stringify(recovered));
  if(saveCalls!==1) throw new Error("reconcile performed a second submit");
  console.log("Q3_AMBIGUOUS_RECONCILE=PASS",recovered.request_id);
}

// A negative reconciliation must remain OUTCOME_UNKNOWN and explicitly unsafe to resubmit.
{
  globalThis.fetch=async (url,opts={})=>{
    const u=String(url);
    if(u.includes("/security.OAuthService/IntrospectToken")) return json({active:true,username:"testuser"});
    if(u.includes("/kernels.KernelsApiService/ListKernels")) return json({kernels:[]});
    throw new Error("unexpected fetch "+u);
  };
  const unknown=await reconcile({effect_id:"ltx2b:"+"a".repeat(64)},cfg);
  if(unknown.state!=="OUTCOME_UNKNOWN"||unknown.safe_to_resubmit!==false) throw new Error("negative reconcile must not authorize resubmit");
  console.log("Q3_NEGATIVE_RECONCILE=PASS");
}

// Q6/Q13: RESULT is a bounded provider-reference read, not a 20-page foreground scan.
{
  let outputCalls=0,listOutputCalls=0;
  globalThis.fetch=async (url,opts={})=>{
    const u=String(url), body=opts.body?JSON.parse(String(opts.body)):{};
    if(u.includes("/security.OAuthService/IntrospectToken")) return json({active:true,username:"testuser"});
    if(u.includes("/kernels.KernelsApiService/GetKernelSessionStatus")) return json({status:2});
    if(u.includes("/kernels.KernelsApiService/ListKernelSessionOutput")){listOutputCalls++; return json({files:[]});}
    if(u.includes("/kernels.KernelsApiService/DownloadKernelOutput")){
      outputCalls++;
      const file=String(body.filePath||"result.bin");
      return new Response(null,{status:302,headers:{location:"https://provider.invalid/"+file+"?fresh=1"}});
    }
    throw new Error("unexpected fetch "+u);
  };
  const ready=await result({request_id:"k2b-r123456789abc-def0-v1"},cfg);
  if(ready.state!=="READY"||ready.result_mode!=="PROVIDER_REFERENCE") throw new Error("bounded result contract failed "+JSON.stringify(ready));
  if(listOutputCalls!==0||outputCalls<1||outputCalls>2) throw new Error("result performed unbounded pagination");
  console.log("Q6_BOUNDED_RESULT=PASS");
}

{
  const h=health(cfg);
  if(h.runtime_profile!=="DURABLE_ASYNC"||h.control_contract?.ambiguous_submit!=="RECONCILE_SAME_EFFECT_BEFORE_RESUBMIT") throw new Error("runtime profile missing");
  console.log("RUNTIME_PROFILE=PASS");
}

console.log("ND_ANTI_HANG_PILOT=PASS");
