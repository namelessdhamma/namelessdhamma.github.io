import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import { createServer } from './server.mjs';
const server=createServer({kaggleToken:'fake',username:'user',bridgeToken:'secret-test-token'});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const base=`http://127.0.0.1:${server.address().port}`;
try{
 let r=await fetch(base+'/health');let j=await r.json();assert.equal(j.service,'nd-kaggle-music-bridge');assert.equal(j.configured,true);
 r=await fetch(base+'/v1/preflight');assert.equal(r.status,401);
 r=await fetch(base+'/v1/submit',{method:'POST',headers:{Authorization:'Bearer secret-test-token','content-type':'application/json'},body:'{}'});assert.equal(r.status,400);
 const sha=x=>crypto.createHash('sha256').update(x).digest('hex');const script='print(1)';const originalKey='niti-ace15-pilot-v3';
 const expected='nd-ace15-'+sha(originalKey+'\n'+sha(script)).slice(0,22);
 assert.match(expected,/^nd-ace15-[0-9a-f]{22}$/);
 const mcpBase={jsonrpc:'2.0',id:7};
 r=await fetch(base+'/mcp',{method:'POST',headers:{authorization:'Bearer secret-test-token','content-type':'application/json'},body:JSON.stringify({...mcpBase,method:'initialize',params:{}})});
 assert.equal(r.status,200);j=await r.json();assert.equal(j.result.serverInfo.name,'nd-kaggle-music-bridge');
 r=await fetch(base+'/mcp',{method:'POST',headers:{authorization:'Bearer secret-test-token','content-type':'application/json'},body:JSON.stringify({...mcpBase,method:'tools/list'})});
 j=await r.json();assert.equal(j.result.tools.length,5);
 console.log('BRIDGE_STATIC_HTTP_CONTRACT=PASS');
}finally{await new Promise(resolve=>server.close(resolve));}
// Isolated NO-GPU admission-truth gate: missing durable endpoint fails closed BEFORE any provider access.
const guarded=createServer({kaggleToken:'mock-not-real',username:'user',bridgeToken:'local-only-test-token',ledgerRequired:true,ledgerUrl:''});
await new Promise(resolve=>guarded.listen(0,'127.0.0.1',resolve));
const guardedUrl=`http://127.0.0.1:${guarded.address().port}`;
try{
 let r=await fetch(guardedUrl+'/health');let j=await r.json();
 assert.equal(j.configured,false);
 assert.equal(j.durable_admission_required,true);
 assert.equal(j.durable_admission_endpoint_configured,false);
 assert.equal(j.durable_admission_live_qualified,false);
 r=await fetch(guardedUrl+'/v1/submit',{method:'POST',
  headers:{authorization:'Bearer local-only-test-token','content-type':'application/json'},
  body:JSON.stringify({idempotency_key:'test-guarded-admission',python_source:'print(1)',confirm_private:true})});
 j=await r.json();
 assert.equal(r.status,503);assert.equal(j.state,'LEDGER_UNAVAILABLE');assert.equal(j.safe_to_resubmit,false);
 console.log('DURABLE_ADMISSION_FAIL_CLOSED_NO_GPU=PASS');
}finally{await new Promise(resolve=>guarded.close(resolve));}
// Every Render build must enforce the music P0 regression and adversarial safety gates.
await import('./qualification_regression.mjs');
await import('./qualification_adversarial.mjs');
