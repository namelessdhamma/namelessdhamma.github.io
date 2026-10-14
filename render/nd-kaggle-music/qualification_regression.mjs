import crypto from 'node:crypto';
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
  if(u.includes('ListKernels')&&options.musicPages){calls.list++;return ok({kernels:options.musicPages[Number(b.page||1)-1]||[]});}
   if(u.includes('ListKernels')){calls.list++;if(options.noVisibility)return ok({kernels:[]}); if(options.slowList)await sleep(options.slowList);return ok({kernels:[...kernels.entries()].filter(([slug])=>slug.includes(b.search)).map(([slug,v])=>({...(options.musicRefOnly?{}:{slug}),ref:'testuser/'+slug,author:'testuser',currentVersionNumber:v}))});}
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
// Live Kaggle ListKernels omits slug on ordinary records. A validated ref MUST work.
await scenario('live_ltx_ref_without_slug_done',{videoCases:[{ref:'testuser/nd-ltx2b-referenceonly',author:'testuser',currentVersionNumber:2}],videoStatus:2},async({call,calls,submitObj})=>{
 const r=await call('/v1/submit',submitObj);
 assert.equal(r.status,202);assert.equal(calls.save,1);
 return {result:'PASS_VERIFIED_REF_ONLY_LTX'};
});
await scenario('live_ltx_ref_without_slug_running',{videoCases:[{ref:'testuser/nd-ltx2b-referenceonly',author:'testuser',currentVersionNumber:2}],videoStatus:1},async({call,calls,submitObj})=>{
 const r=await call('/v1/submit',submitObj);
 assert.equal(r.status,409);assert.equal(r.body.reason,'VIDEO_GPU_ACTIVE_OR_UNKNOWN');assert.equal(calls.save,0);
 return {result:'PASS_REF_ONLY_LTX_RUNNING_DENIED'};
});
await scenario('foreign_ltx_ref_rejected',{videoCases:[{ref:'anotheruser/nd-ltx2b-other',author:'anotheruser',currentVersionNumber:2}]},async({call,calls,submitObj})=>{
 const r=await call('/v1/submit',submitObj);
 assert.equal(r.status,409);assert.equal(r.body.reason,'VIDEO_SLUG_UNKNOWN');assert.equal(calls.save,0);
 return {result:'PASS_FOREIGN_REF_UNKNOWN_FAIL_CLOSED'};
});
await scenario('music_ref_only_reuse',{musicRefOnly:true},async({call,calls,submitObj})=>{
 const a=await call('/v1/submit',submitObj),b=await call('/v1/submit',submitObj);
 assert.equal(a.status,202);assert.equal(b.status,200);assert.equal(a.body.job_id,b.body.job_id);assert.equal(calls.save,1);
 return {result:'PASS_REAL_PROVIDER_REF_ONLY_MUSIC_REUSE'};
});
const ltx109=Array.from({length:109},(_,i)=>({ref:'testuser/nd-ltx2b-direct-qa'+String(i).padStart(3,'0'),author:'testuser',currentVersionNumber:1}));
const pages114=[ltx109.slice(0,50),ltx109.slice(50,100),[...ltx109.slice(100),...Array.from({length:5},(_,j)=>({title:'unrelated unnamed '+j,note:true}))]];
await scenario('large_paged_ref_only_ltx_cached',{videoPages:pages114,videoStatus:2},async({call,calls,submitObj})=>{
 const a=await call('/v1/submit',submitObj);
 assert.equal(a.status,202);assert.equal(calls.status,109);assert.equal(calls.save,1);
 const second={...submitObj,idempotency_key:submitObj.idempotency_key+'-other'};
 const b=await call('/v1/submit',second);
 assert.equal(b.status,202);assert.equal(calls.status,109);assert.equal(calls.save,2);
 return {result:'PASS_114_ROWS_109_REF_ONLY_TERMINAL_CACHE',status_reads:calls.status};
});
const previousSlug=(o)=>'nd-ace15-'+crypto.createHash('sha256').update(o.idempotency_key+'\n'+crypto.createHash('sha256').update(o.python_source).digest('hex')).digest('hex').slice(0,22);
const unrelated100=Array.from({length:100},(_,i)=>({ref:'testuser/unrelated-'+i,author:'testuser',currentVersionNumber:1}));
await scenario('music_exact_ref_on_third_page',{musicPages:[unrelated100.slice(0,50),unrelated100.slice(50,100),{pending:true}]},async({call,calls,submitObj,options})=>{
 const slug=previousSlug(submitObj);
 options.musicPages[2]=[{ref:'testuser/'+slug,author:'testuser',currentVersionNumber:3}];
 const a=await call('/v1/submit',submitObj);
 assert.equal(a.status,200);assert.equal(a.body.reused_existing,true);assert.equal(calls.save,0);assert.equal(calls.list,3);
 return {result:'PASS_EXISTING_MUSIC_REF_PAGE3_NO_RESUBMIT'};
});
await scenario('music_search_history_incomplete',{musicPages:Array.from({length:10},(_,p)=>unrelated100.slice(0,50).map((k,i)=>({ref:'testuser/history-'+p+'-'+i,author:'testuser'})))},async({call,calls,submitObj})=>{
 const a=await call('/v1/submit',submitObj);
 assert.equal(a.status,503);assert.equal(a.body.safe_to_resubmit,false);assert.equal(calls.save,0);
 return {result:'PASS_NO_SAVE_ON_INCOMPLETE_EFFECT_SEARCH'};
});
await scenario('music_search_missing_after_complete_pages',{musicPages:[unrelated100.slice(0,50),unrelated100.slice(50,100),[]]},async({call,calls,submitObj})=>{
 const a=await call('/v1/submit',submitObj);
 assert.equal(a.status,202);assert.equal(calls.save,1);return {result:'PASS_COMPLETE_THREE_PAGE_SEARCH_PERMITS_SAFE_CLAIM'};
});
process.stdout.write(JSON.stringify(harness,null,2)+'\n');