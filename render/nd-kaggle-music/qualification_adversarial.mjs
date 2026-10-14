import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import {createServer} from './server.mjs';
const nativeFetch=globalThis.fetch, results=[];
const ok=o=>new Response(JSON.stringify(o),{status:200,headers:{'content-type':'application/json'}});
const bad=(status,msg='FAIL')=>new Response(JSON.stringify({message:msg}),{status,headers:{'content-type':'application/json'}});
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function test(name,flags,work){
 let calls={save:0,list:0,identity:0,quota:0,status:0,out:0};let kernels=new Map();
 globalThis.fetch=async(url,opt={})=>{
  if(!String(url).includes('api.kaggle.com'))return nativeFetch(url,opt);
  const body=JSON.parse(opt.body||'{}'),u=String(url);
  if(u.includes('IntrospectToken')){calls.identity++;return flags.invalidAuth?bad(401,'invalid'):ok({active:true,username:'testuser'});}
  if(u.includes('GetAcceleratorQuotaStatistics')){calls.quota++;return flags.quotaErr?bad(flags.quotaErr,'FULL'):ok({gpuQuota:{timeUsed:'0s',timeReserved:'0s',totalTimeAllowed:`${flags.quotaSeconds??108000}s`}});}
  if(u.includes('ListKernels')){calls.list++;if(flags.listErr)return bad(flags.listErr,'NOT_VISIBLE');if(flags.slowList)await sleep(flags.slowList);if(flags.invisible)return ok({kernels:[]});return ok({kernels:[...kernels.entries()].map(([slug,v])=>({slug,ref:'testuser/'+slug,currentVersionNumber:v})).filter(x=>!body.search||x.slug===body.search)});}
  if(u.includes('SaveKernel')){calls.save++;if(flags.slowSave)await sleep(flags.slowSave);if(flags.hardSaveFail)return bad(flags.hardSaveFail,'response_lost');let slug=body.slug.split('/').pop();kernels.set(slug,1);if(flags.saveCommitResponseLost)return bad(503,'save accepted but ack lost');return ok({versionNumber:1});}
  if(u.includes('GetKernelSessionStatus')){calls.status++;if(flags.visibility403)return bad(403,'PERMISSION_DENIED');return ok({status:flags.state??1});}
  if(u.includes('DownloadKernelOutput')){calls.out++;return ok({url:'https://example.org/synthetic-qa-result.wav?no-real-audio=1'});}
  throw Error('Unexpected mock endpoint '+u);
 };
 let srv=createServer({kaggleToken:'FAKE_UNIT_TOKEN',username:'testuser',bridgeToken:'FAKE_BRIDGE_KEY'});
 await new Promise(resolve=>srv.listen(0,'127.0.0.1',resolve));
 const base=`http://127.0.0.1:${srv.address().port}`;
 async function call(path,body,opts={}){let r=await nativeFetch(base+path,{method:'POST',headers:{Authorization:'Bearer FAKE_BRIDGE_KEY','content-type':'application/json'},body:JSON.stringify(body),...opts});return {status:r.status,data:await r.json()};}
 const payload={idempotency_key:'adversarial-'+name,python_source:'print("synthetic QA only; no user content")',confirm_private:true};
 try{const verdict=await work({call,payload,calls,kernels,flags,base});results.push({name,verdict,...calls});}
 finally{await new Promise(resolve=>srv.close(resolve));globalThis.fetch=nativeFetch;}
}
await test('concurrent_40',{slowList:25,slowSave:80},async({call,payload,calls})=>{const arr=await Promise.all(Array.from({length:40},()=>call('/v1/submit',payload)));assert.equal(calls.save,1);assert.equal(new Set(arr.map(x=>x.data.job_id)).size,1);return 'PASS_INPROCESS_SINGLE_FLIGHT_40';});
await test('ambiguous_quarantine',{hardSaveFail:503},async({call,payload,calls})=>{let a=await call('/v1/submit',payload);assert.equal(a.data.state,'SUBMIT_OUTCOME_UNKNOWN');let b=await call('/v1/submit',payload);assert.equal(b.data.state,'OUTCOME_UNKNOWN');assert.equal(calls.save,1);return 'PASS_NO_RETRY_AMBIGUOUS';});
await test('commit_ack_lost_reconcile',{saveCommitResponseLost:true},async({call,payload,calls,flags})=>{let a=await call('/v1/submit',payload);assert.equal(a.data.state,'SUBMIT_OUTCOME_UNKNOWN');let hash=crypto.createHash('sha256').update(payload.python_source).digest('hex');let b=await call('/v1/reconcile',{idempotency_key:payload.idempotency_key,source_sha256:hash});assert.equal(b.data.ok,true);assert.equal(b.data.state,'RUNNING');let c=await call('/v1/submit',payload);assert.equal(c.data.reused_existing,true);assert.equal(calls.save,1);return 'PASS_RECONCILE_LOST_ACK';});
await test('status_403_both',{visibility403:true},async({call,payload,calls})=>{let a=await call('/v1/submit',payload);let b=await call('/v1/status',{job_id:a.data.job_id});let c=await call('/v1/result',{job_id:a.data.job_id});assert.equal(b.data.state,'PROVIDER_VISIBILITY_PENDING');assert.equal(c.data.state,'PROVIDER_VISIBILITY_PENDING');assert.equal(b.data.safe_to_resubmit,false);assert.equal(calls.save,1);return 'PASS_VISIBILITY_PENDING_TYPED';});
await test('provider_no_quota',{quotaErr:429},async({call,payload,calls})=>{let x=await call('/v1/submit',payload);assert.equal(calls.save,0);assert.equal(x.data.ok,false);return 'PASS_QUOTA_PROVIDER_FAIL_CLOSED';});
await test('provider_list_403',{listErr:403},async({call,payload,calls})=>{let x=await call('/v1/submit',payload);assert.equal(x.data.state,'OUTCOME_UNKNOWN');assert.equal(calls.save,0);return 'PASS_LIST_VISIBILITY_FAIL_CLOSED';});
await test('auth_mismatch',{invalidAuth:true},async({call,payload,calls})=>{let x=await call('/v1/submit',payload);assert.equal(calls.save,0);assert.equal(x.data.ok,false);return 'PASS_AUTH_FAIL_CLOSED';});
await test('result_completed',{state:2},async({call,payload,calls})=>{let a=await call('/v1/submit',payload),b=await call('/v1/result',{job_id:a.data.job_id});assert.equal(b.data.ok,true);assert.equal(b.data.expires_with_provider,true);assert.equal(calls.out,1);return 'PASS_EXPIRING_RESULT_REFERENCE_ONLY';});
await test('nonterminal_no_result',{state:1},async({call,payload,calls})=>{let a=await call('/v1/submit',payload),b=await call('/v1/result',{job_id:a.data.job_id});assert.equal(b.data.ok,false);assert.equal(calls.out,0);return 'PASS_NO_PREMATURE_READY';});
console.log(JSON.stringify({tests:results.length,passes:results.filter(x=>x.verdict.startsWith('PASS')).length,real_gpu_runs:0,items:results},null,2));