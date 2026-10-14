import assert from 'node:assert/strict';
import {createServer} from './server.mjs';
const nativeFetch=globalThis.fetch;
const harness=[];
const sleep=(n)=>new Promise(r=>setTimeout(r,n));
const ok=obj=>new Response(JSON.stringify(obj),{status:200,headers:{'content-type':'application/json'}});
async function scenario(label, options, test){
 const calls={save:0,list:0,intro:0,quota:0,status:0};
 const kernels=new Map();
 globalThis.fetch=async(url,opt={})=>{
  let u=String(url);
  if(!u.includes('api.kaggle.com'))return nativeFetch(url,opt);
  const b=JSON.parse(opt.body||'{}');
  if(u.includes('IntrospectToken')){calls.intro++;return ok({active:true,username:'testuser'});}
  if(u.includes('GetAcceleratorQuotaStatistics')){calls.quota++;return ok({gpuQuota:{timeUsed:'0s',timeReserved:`${options.reservedSeconds??0}s`,totalTimeAllowed:options.quotaSeconds===undefined?'108000s':`${options.quotaSeconds}s`}});}
  if(u.includes('ListKernels')&&b.search==='nd-ltx2b'){calls.list++;return ok({kernels:options.videoPages?(options.videoPages[Number(b.page||1)-1]||[]):(options.videoCases||[])});}
  if(u.includes('ListKernels')){calls.list++;if(options.noVisibility)return ok({kernels:[]}); if(options.slowList)await sleep(options.slowList);return ok({kernels:[...kernels.entries()].filter(([slug])=>slug.includes(b.search)).map(([slug,v])=>({slug,ref:'testuser/'+slug,currentVersionNumber:v}))});}
  if(u.includes('SaveKernel')){calls.save++;if(options.saveDelay)await sleep(options.saveDelay);if(options.saveStatus)return new Response('{}',{status:options.saveStatus,headers:{'content-type':'application/json'}});const slug=b.slug.split('/').pop();kernels.set(slug,1);return ok({versionNumber:1});}
  if(u.includes('GetKernelSessionStatus')&&String(b.kernelSlug||'').startsWith('nd-ltx2b-')){calls.status++;if(options.videoVisibility403)return new Response('{"message":"PERMISSION_DENIED"}',{status:403,headers:{'content-type':'application/json'}});return ok({status:options.videoStatus===undefined?1:options.videoStatus});}
  if(u.includes('GetKernelSessionStatus')){calls.status++;if(options.visibility403)return new Response('{"message":"PERMISSION_DENIED"}',{status:403,headers:{'content-type':'application/json'}});return ok({status:1});}
  throw Error('Unexpected mocked provider API '+u);
 };
 const srv=createServer({kaggleToken:'FAKE_TEST_TOKEN',username:'testuser',bridgeToken:'FAKE_GATEWAY_KEY'});
 await new Promise(resolve=>srv.listen(0,'127.0.0.1',resolve));
 const base='http://127.0.0.1:'+srv.address().port;
 const call=async(path,obj)=>{const res=await nativeFetch(base+path,{method:'POST',headers:{authorization:'Bearer FAKE_GATEWAY_KEY','content-type':'application/json'},body:JSON.stringify(obj)});return {status:res.status,body:await res.json()};};
 const submitObj={idempotency_key:'qa-'+label,python_source:'print("not a real song")',confirm_private:true};
 try {const result=await test({call,calls,submitObj,options});harness.push({scenario:label,...result,calls});}
 finally{await new Promise(resolve=>srv.close(resolve)); globalThis.fetch=nativeFetch;}
}
await scenario('auth_and_no_gpu_action',{},async({call,calls,submitObj})=>{const r=await call('/v1/submit',{...submitObj,confirm_private:false});assert.equal(r.status,400);assert.equal(calls.save,0);return {result:'PASS_REJECTION',response:r.body.error};});
await scenario('first_submit_and_reuse',{},async({call,calls,submitObj})=>{const a=await call('/v1/submit',submitObj);const b=await call('/v1/submit',submitObj);assert.equal(a.status,202);assert.equal(b.status,200);assert.equal(calls.save,1);assert.equal(a.body.job_id,b.body.job_id);return {result:'PASS_DEDUP_SEQUENTIAL',jobRef:'redacted'};});
await scenario('parallel_duplicate_submit',{slowList:20,saveDelay:30},async({call,calls,submitObj})=>{const [a,b]=await Promise.all([call('/v1/submit',submitObj),call('/v1/submit',submitObj)]);return {result:calls.save===1?'PASS_ATOMIC_SINGLE_FLIGHT':'FAIL_DOUBLE_PROVIDER_SUBMIT',saveCalls:calls.save,statuses:[a.status,b.status]};});
await scenario('quota_exhaustion',{quotaSeconds:600},async({call,calls,submitObj})=>{const a=await call('/v1/submit',submitObj);assert.equal(a.body.state,'CAPACITY_BLOCKED');assert.equal(calls.save,0);return {result:'PASS_FREE_ONLY_QUOTA_GUARD',status:a.status};});
await scenario('save_unknown',{saveStatus:503,noVisibility:true},async({call,calls,submitObj})=>{const a=await call('/v1/submit',submitObj);return {result:a.body.state==='SUBMIT_OUTCOME_UNKNOWN'&&a.body.safe_to_resubmit===false?'PASS_AMBIGUOUS_REPORTED':'FAIL_UNSAFE_RESUBMIT',status:a.status,saveCalls:calls.save};});
await scenario('provider_kernel_403_visibility',{visibility403:true},async({call,calls,submitObj})=>{const a=await call('/v1/submit',submitObj);const b=await call('/v1/status',{job_id:a.body.job_id});return {result:b.body.state==='PROVIDER_VISIBILITY_PENDING'?'PASS_VISIBILITY_GRACE':'FAIL_UNTYPED_403',status:b.status,error_code:String(b.body.error||'').slice(0,60)};});

const video=[{slug:'nd-ltx2b-admission-fixture',ref:'testuser/nd-ltx2b-admission-fixture',currentVersionNumber:1}];
await scenario('video_active_blocks_music',{videoCases:video,videoStatus:1},async({call,calls,submitObj})=>{
 const r=await call('/v1/submit',submitObj);
 assert.equal(r.status,409);assert.equal(r.body.state,'SHARED_GPU_ADMISSION_BLOCKED');assert.equal(r.body.safe_to_resubmit,false);assert.equal(calls.save,0);
 return {result:'PASS_NO_MUSIC_WHILE_LTX_RUNNING'};
});
await scenario('video_completed_allows_music',{videoCases:video,videoStatus:2},async({call,calls,submitObj})=>{
 const r=await call('/v1/submit',submitObj);
 assert.equal(r.status,202);assert.equal(calls.save,1);
 return {result:'PASS_READONLY_LTX_COMPLETED'};
});
await scenario('video_unknown_blocks_music',{videoCases:video,videoStatus:0},async({call,calls,submitObj})=>{
 const r=await call('/v1/submit',submitObj);
 assert.equal(r.status,409);assert.equal(r.body.state,'SHARED_GPU_ADMISSION_BLOCKED');assert.equal(calls.save,0);
 return {result:'PASS_LTX_UNKNOWN_FAIL_CLOSED'};
});
await scenario('video_visibility_403_blocks_music',{videoCases:video,videoVisibility403:true},async({call,calls,submitObj})=>{
 const r=await call('/v1/submit',submitObj);
 assert.equal(r.status,409);assert.equal(r.body.state,'SHARED_GPU_ADMISSION_BLOCKED');assert.equal(calls.save,0);
 return {result:'PASS_LTX_INVISIBLE_FAIL_CLOSED'};
});

// LIVE-OBSERVED CASE: Kaggle account history is 50+ rows, with five title-only placeholders.
const genericHistory=Array.from({length:50},(_,i)=>({slug:'history-'+i,ref:'testuser/history-'+i,currentVersionNumber:1}));
const titleOnly=Array.from({length:5},(_,i)=>({title:'unrelated note '+i,otherField:true}));
await scenario('video_history_two_pages_allows_neutral',{videoPages:[genericHistory,titleOnly]},async({call,calls,submitObj})=>{
 const a=await call('/v1/submit',submitObj);
 assert.equal(a.status,202);assert.equal(calls.save,1);assert(calls.list>=3);
 return {result:'PASS_COMPLETE_PAGED_READONLY_HISTORY',pages:2};
});
await scenario('title_only_ltx_blocks',{videoCases:[{title:'ND LTX missing id and slug',otherField:true}]},async({call,calls,submitObj})=>{
 const a=await call('/v1/submit',submitObj);
 assert.equal(a.status,409);assert.equal(a.body.reason,'VIDEO_UNKNOWN_TITLE_ROW');assert.equal(calls.save,0);
 return {result:'PASS_UNKNOWN_VIDEO_TITLE_FAIL_CLOSED'};
});
await scenario('shared_quota_reserved_blocks',{reservedSeconds:90},async({call,calls,submitObj})=>{
 const a=await call('/v1/submit',submitObj);
 assert.equal(a.status,409);assert.equal(a.body.reason,'SHARED_GPU_RESERVATION_ACTIVE');assert.equal(calls.save,0);
 return {result:'PASS_RESERVED_GPU_FAIL_CLOSED'};
});
await scenario('cancel_requested_is_not_terminal',{videoCases:video,videoStatus:4},async({call,calls,submitObj})=>{
 const a=await call('/v1/submit',submitObj);
 assert.equal(a.status,409);assert.equal(a.body.reason,'VIDEO_GPU_ACTIVE_OR_UNKNOWN');assert.equal(calls.save,0);
 return {result:'PASS_CANCEL_REQUESTED_NONTERMINAL'};
});
await scenario('page_limit_fails_closed',{videoPages:Array.from({length:10},(_,p)=>genericHistory.map((k,i)=>({slug:'history-'+p+'-'+i,ref:'testuser/history-'+p+'-'+i,currentVersionNumber:1})))},async({call,calls,submitObj})=>{
 const a=await call('/v1/submit',submitObj);
 assert.equal(a.status,409);assert.equal(a.body.reason,'VIDEO_SCAN_INCOMPLETE');assert.equal(calls.save,0);
 return {result:'PASS_BOUNDED_LIST_PAGINATION_DENIAL'};
});
await scenario('repeated_ltx_ref_on_next_page_blocks',{videoPages:[genericHistory.map((x,i)=>i===0?video[0]:x),[video[0]]]},async({call,calls,submitObj})=>{
 const a=await call('/v1/submit',submitObj);
 assert.equal(a.status,409);assert.equal(a.body.reason,'VIDEO_PAGE_DUPLICATE');assert.equal(calls.save,0);
 return {result:'PASS_CROSS_PAGE_DUPLICATE_DENIED'};
});
process.stdout.write(JSON.stringify(harness,null,2)+'\n');