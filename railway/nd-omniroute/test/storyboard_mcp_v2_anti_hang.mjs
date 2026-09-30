import assert from 'node:assert/strict';

process.env.ND_GITHUB_PAT='test-token';
process.env.ND_STORYBOARD_SUBMIT_TIMEOUT_MS='90';
process.env.ND_STORYBOARD_STATUS_TIMEOUT_MS='80';
process.env.ND_STORYBOARD_RESULT_TIMEOUT_MS='80';
process.env.ND_STORYBOARD_RECONCILE_TIMEOUT_MS='80';
process.env.ND_STORYBOARD_CONTROL_BRANCH='main';

const m=await import('../storyboard_mcp_v2.mjs?test='+Date.now());
const args={
  frames:[
    {url:'https://example.org/a.jpg',duration:1,motion:'slow_push_in',transition:'fade'},
    {url:'https://example.org/b.jpg',duration:1,motion:'slow_pull_out',transition:'cut'}
  ],
  width:640,height:360,fps:24,idempotency_key:'same-logical-render'
};
const e1=m.storyboardEffect(args), e2=m.storyboardEffect(args);
assert.equal(e1.effect_id,e2.effect_id);
assert.equal(e1.request_id,e2.request_id);
console.log('SB_EFFECT_IDENTITY=PASS',e1.request_id);

const json=(o,status=200)=>new Response(JSON.stringify(o),{status,headers:{'content-type':'application/json'}});
function hanging(signal){
  return new Response(new ReadableStream({
    start(controller){
      signal?.addEventListener('abort',()=>{try{controller.error(signal.reason||new Error('aborted'));}catch{}},{once:true});
    }
  }),{status:200,headers:{'content-type':'application/json'}});
}

let record=null, acceptedCreates=0, putCalls=0, runs=[], artifactZipCalls=0;
globalThis.fetch=async (url,opts={})=>{
  const u=String(url);
  if(u.includes('/contents/.nd-control/storyboard/requests/')){
    if((opts.method||'GET')==='PUT'){
      putCalls++;
      const body=JSON.parse(String(opts.body||'{}'));
      const decoded=JSON.parse(Buffer.from(body.content,'base64').toString('utf8'));
      if(record)return json({message:'already exists'},422);
      record=decoded;acceptedCreates++;
      return json({content:{html_url:'https://github.invalid/request'},commit:{sha:'c1'}},201);
    }
    if(!record)return json({message:'Not Found'},404);
    return json({sha:'blob1',html_url:'https://github.invalid/request',content:Buffer.from(JSON.stringify(record)).toString('base64')});
  }
  if(u.includes('/actions/workflows/nd-storyboard-render.yml/runs')){
    return json({workflow_runs:runs});
  }
  if(u.includes('/actions/runs/')&&u.endsWith('/artifacts')){
    return json({artifacts:[{id:77,name:'nd-storyboard-'+e1.request_id,size_in_bytes:1024,expired:false,archive_download_url:'https://api.github.invalid/artifact'}]});
  }
  if(u.includes('/actions/artifacts/')&&u.endsWith('/zip')){artifactZipCalls++;return json({unexpected:true});}
  throw new Error('unexpected fetch '+u);
};

// Overlapping exact submits: one durable create can win; the other can only reuse it.
const [a,b]=await Promise.all([m.storyboardRenderSubmit(args),m.storyboardRenderSubmit(args)]);
assert.equal(acceptedCreates,1);
assert.equal(a.effect_id,b.effect_id);
assert.equal(a.request_id,b.request_id);
assert.equal([a.state,b.state].includes('SUBMITTED'),true);
assert.equal([a.reused_existing,b.reused_existing].includes(true),true);
console.log('SB_OVERLAPPING_WAKE=PASS',putCalls,acceptedCreates);

// Lost create response after provider acceptance: return ambiguous with same effect, then reconcile without new PUT.
record=null;acceptedCreates=0;putCalls=0;runs=[];
globalThis.fetch=async (url,opts={})=>{
  const u=String(url);
  if(u.includes('/contents/.nd-control/storyboard/requests/')){
    if((opts.method||'GET')==='PUT'){
      putCalls++;
      const body=JSON.parse(String(opts.body||'{}'));
      record=JSON.parse(Buffer.from(body.content,'base64').toString('utf8'));
      acceptedCreates++;
      return hanging(opts.signal);
    }
    if(!record)return json({message:'Not Found'},404);
    return json({sha:'blob2',html_url:'https://github.invalid/request2',content:Buffer.from(JSON.stringify(record)).toString('base64')});
  }
  if(u.includes('/actions/workflows/nd-storyboard-render.yml/runs'))return json({workflow_runs:[]});
  throw new Error('unexpected fetch '+u);
};
const ambiguous=await m.storyboardRenderSubmit(args);
assert.equal(ambiguous.state,'SUBMIT_AMBIGUOUS');
assert.equal(ambiguous.outcome_state,'OUTCOME_UNKNOWN');
assert.equal(ambiguous.safe_to_resubmit,false);
assert.equal(acceptedCreates,1);
const before=putCalls;
const recovered=await m.storyboardRenderReconcile({effect_id:ambiguous.effect_id});
assert.equal(recovered.effect_id,ambiguous.effect_id);
assert.equal(recovered.request_id,ambiguous.request_id);
assert.equal(recovered.reconciled,true);
assert.equal(putCalls,before);
console.log('SB_AMBIGUOUS_RECONCILE=PASS');

// Negative reconciliation never authorizes blind resubmit.
record=null;
const negative=await m.storyboardRenderReconcile({effect_id:e1.effect_id});
assert.equal(negative.state,'OUTCOME_UNKNOWN');
assert.equal(negative.safe_to_resubmit,false);
console.log('SB_NEGATIVE_RECONCILE=PASS');

// STATUS body hang is bounded and aborts managed I/O.
let statusSignal=null;
globalThis.fetch=async (url,opts={})=>{
  const u=String(url);
  if(u.includes('/actions/workflows/nd-storyboard-render.yml/runs')){statusSignal=opts.signal;return hanging(opts.signal);}
  throw new Error('unexpected fetch '+u);
};
let caught=null;const started=Date.now();
try{await m.storyboardRenderStatus({request_id:e1.request_id});}catch(err){caught=err;}
assert.equal(caught?.code,'CONTROL_DEADLINE');
assert.equal(statusSignal?.aborted,true);
assert.ok(Date.now()-started<500);
console.log('SB_STATUS_DEADLINE=PASS');

// RESULT is metadata/reference only and never downloads the artifact ZIP.
runs=[{id:999,name:'ND Storyboard Renderer',display_title:'ND Storyboard '+e1.request_id,status:'completed',conclusion:'success',html_url:'https://github.invalid/run/999'}];
artifactZipCalls=0;
globalThis.fetch=async (url,opts={})=>{
  const u=String(url);
  if(u.includes('/actions/workflows/nd-storyboard-render.yml/runs'))return json({workflow_runs:runs});
  if(u.includes('/actions/runs/999/artifacts'))return json({artifacts:[{id:77,name:'nd-storyboard-'+e1.request_id,size_in_bytes:1024,expired:false,archive_download_url:'https://api.github.invalid/artifact'}]});
  if(u.includes('/actions/artifacts/77/zip')){artifactZipCalls++;return json({unexpected:true});}
  throw new Error('unexpected fetch '+u);
};
const ready=await m.storyboardRenderResult({request_id:e1.request_id});
assert.equal(ready.state,'READY');
assert.equal(ready.result_mode,'PROVIDER_REFERENCE');
assert.equal(artifactZipCalls,0);
assert.ok(String(ready.mp4_url).includes('/storyboard-result/'));
console.log('SB_REFERENCE_RESULT=PASS');

const health=await m.storyboardHealth();
assert.equal(health.runtime_profile,'DURABLE_ASYNC');
assert.equal(health.control_contract.ambiguous_submit,'RECONCILE_SAME_EFFECT_BEFORE_RESUBMIT');
console.log('STORYBOARD_ANTI_HANG_V2=PASS');
