import assert from 'node:assert/strict';

process.env.ND_GITHUB_PAT='test-token';
process.env.ND_STORYBOARD_SUBMIT_TIMEOUT_MS='90';
process.env.ND_STORYBOARD_STATUS_TIMEOUT_MS='80';
process.env.ND_STORYBOARD_RESULT_TIMEOUT_MS='80';
process.env.ND_STORYBOARD_RECONCILE_TIMEOUT_MS='80';
process.env.ND_STORYBOARD_SOURCE_BRANCH='main';

const m=await import('../storyboard_mcp_v2.mjs?test='+Date.now());
const args={
  frames:[
    {url:'https://example.org/a.jpg',duration:1,motion:'slow_push_in',transition:'fade'},
    {url:'https://example.org/b.jpg',duration:1,motion:'slow_pull_out',transition:'cut'}
  ],
  width:640,height:360,fps:24,idempotency_key:'same-logical-render'
};
const effect=m.storyboardEffect(args);
assert.equal(effect.effect_id,m.storyboardEffect(args).effect_id);
assert.ok(effect.request_tag.includes(effect.request_id));
console.log('SB_EFFECT_IDENTITY=PASS',effect.request_id);

const json=(o,status=200)=>new Response(JSON.stringify(o),{status,headers:{'content-type':'application/json'}});
function hanging(signal){
  return new Response(new ReadableStream({
    start(controller){signal?.addEventListener('abort',()=>{try{controller.error(signal.reason||new Error('aborted'));}catch{}},{once:true});}
  }),{status:200,headers:{'content-type':'application/json'}});
}

const baseSha='1111111111111111111111111111111111111111';
let tagRef=null,tagObjectCalls=0,refCreateCalls=0,acceptedRefs=0,runs=[],artifactZipCalls=0;
function commonFetch(url,opts={}){
  const u=String(url),method=String(opts.method||'GET').toUpperCase();
  if(u.includes('/git/ref/heads/main')) return json({ref:'refs/heads/main',object:{sha:baseSha,type:'commit'}});
  if(u.includes('/actions/workflows/nd-storyboard-render.yml/runs')) return json({workflow_runs:runs});
  if(u.includes('/actions/runs/999/artifacts')) return json({artifacts:[{id:77,name:'nd-storyboard-'+effect.request_id,size_in_bytes:1024,expired:false,archive_download_url:'https://api.github.invalid/artifact'}]});
  if(u.includes('/actions/artifacts/77/zip')){artifactZipCalls++;return json({unexpected:true});}
  return null;
}

globalThis.fetch=async (url,opts={})=>{
  const u=String(url),method=String(opts.method||'GET').toUpperCase();
  const common=commonFetch(url,opts); if(common)return common;
  if(u.includes('/git/ref/tags/')){
    if(!tagRef)return json({message:'Not Found'},404);
    return json({ref:'refs/tags/'+effect.request_tag,object:{sha:tagRef,type:'tag'}});
  }
  if(u.endsWith('/git/tags')&&method==='POST'){tagObjectCalls++;return json({sha:String(tagObjectCalls).padStart(40,'a').slice(-40)},201);}
  if(u.endsWith('/git/refs')&&method==='POST'){
    refCreateCalls++;
    if(tagRef)return json({message:'Reference already exists'},422);
    const body=JSON.parse(String(opts.body||'{}'));tagRef=body.sha;acceptedRefs++;
    return json({ref:body.ref,object:{sha:body.sha,type:'tag'}},201);
  }
  throw new Error('unexpected fetch '+method+' '+u);
};

const [a,b]=await Promise.all([m.storyboardRenderSubmit(args),m.storyboardRenderSubmit(args)]);
assert.equal(acceptedRefs,1);
assert.equal(a.effect_id,b.effect_id);
assert.equal(a.request_id,b.request_id);
assert.equal([a.state,b.state].includes('SUBMITTED'),true);
assert.equal([a.reused_existing,b.reused_existing].includes(true),true);
console.log('SB_OVERLAPPING_WAKE=PASS',refCreateCalls,acceptedRefs);

// Provider accepts the unique tag ref but the response body is lost.
tagRef=null;tagObjectCalls=0;refCreateCalls=0;acceptedRefs=0;runs=[];
globalThis.fetch=async (url,opts={})=>{
  const u=String(url),method=String(opts.method||'GET').toUpperCase();
  const common=commonFetch(url,opts); if(common)return common;
  if(u.includes('/git/ref/tags/')){
    if(!tagRef)return json({message:'Not Found'},404);
    return json({ref:'refs/tags/'+effect.request_tag,object:{sha:tagRef,type:'tag'}});
  }
  if(u.endsWith('/git/tags')&&method==='POST'){tagObjectCalls++;return json({sha:'2222222222222222222222222222222222222222'},201);}
  if(u.endsWith('/git/refs')&&method==='POST'){
    refCreateCalls++;tagRef='2222222222222222222222222222222222222222';acceptedRefs++;
    return hanging(opts.signal);
  }
  throw new Error('unexpected fetch '+method+' '+u);
};
const ambiguous=await m.storyboardRenderSubmit(args);
assert.equal(ambiguous.state,'SUBMIT_AMBIGUOUS');
assert.equal(ambiguous.outcome_state,'OUTCOME_UNKNOWN');
assert.equal(ambiguous.safe_to_resubmit,false);
assert.equal(acceptedRefs,1);
const before=refCreateCalls;
const recovered=await m.storyboardRenderReconcile({effect_id:ambiguous.effect_id});
assert.equal(recovered.effect_id,ambiguous.effect_id);
assert.equal(recovered.reconciled,true);
assert.equal(refCreateCalls,before);
console.log('SB_AMBIGUOUS_RECONCILE=PASS');

// Negative reconciliation does not authorize a blind render retry.
tagRef=null;
const negative=await m.storyboardRenderReconcile({effect_id:effect.effect_id});
assert.equal(negative.state,'OUTCOME_UNKNOWN');
assert.equal(negative.safe_to_resubmit,false);
console.log('SB_NEGATIVE_RECONCILE=PASS');

// Hanging status body must abort managed I/O.
let statusSignal=null;
globalThis.fetch=async (url,opts={})=>{
  const u=String(url);
  if(u.includes('/actions/workflows/nd-storyboard-render.yml/runs')){statusSignal=opts.signal;return hanging(opts.signal);}
  throw new Error('unexpected fetch '+u);
};
let caught=null;const started=Date.now();
try{await m.storyboardRenderStatus({request_id:effect.request_id});}catch(err){caught=err;}
assert.equal(caught?.code,'CONTROL_DEADLINE');
assert.equal(statusSignal?.aborted,true);
assert.ok(Date.now()-started<500);
console.log('SB_STATUS_DEADLINE=PASS');

// RESULT stays reference-only.
runs=[{id:999,display_title:'ND Storyboard nd-storyboard/'+effect.request_id+'-tail',status:'completed',conclusion:'success',html_url:'https://github.invalid/run/999'}];
artifactZipCalls=0;
globalThis.fetch=async (url,opts={})=>{
  const common=commonFetch(url,opts);if(common)return common;
  throw new Error('unexpected fetch '+String(url));
};
const ready=await m.storyboardRenderResult({request_id:effect.request_id});
assert.equal(ready.state,'READY');
assert.equal(ready.result_mode,'PROVIDER_REFERENCE');
assert.equal(artifactZipCalls,0);
assert.ok(String(ready.mp4_url).includes('/storyboard-result/'));
console.log('SB_REFERENCE_RESULT=PASS');

const health=await m.storyboardHealth();
assert.equal(health.runtime_profile,'DURABLE_ASYNC');
assert.equal(health.control_contract.ambiguous_submit,'RECONCILE_SAME_EFFECT_BEFORE_RESUBMIT');
console.log('STORYBOARD_ANTI_HANG_V2=PASS');
