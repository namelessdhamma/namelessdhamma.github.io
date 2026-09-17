import test from 'node:test';
import assert from 'node:assert/strict';
import { goSearchResponse, normalizeGoSearch } from './gosearch_core.mjs';
import { createRpc } from './mcp_core.mjs';

test('goSearchResponse posts a bounded Agent request with cgid and bearer auth', async () => {
  const seen = {};
  const fetchImpl = async (url, init) => {
    seen.url = url;
    seen.init = init;
    return new Response(JSON.stringify({completion:{message:'found'},conversationId:42}), {status:200, headers:{'content-type':'application/json'}});
  };
  const out = await goSearchResponse({query:'find mnemonic context', apiToken:'tok', cgid:'123', fetchImpl});
  assert.equal(seen.url, 'https://api.gosearch.ai/goai/response');
  assert.equal(seen.init.method, 'POST');
  assert.equal(seen.init.headers.Authorization, 'Bearer tok');
  assert.match(seen.init.headers['Content-Type'], /application\/x-www-form-urlencoded/);
  const form = new URLSearchParams(seen.init.body);
  assert.equal(form.get('prompt'), 'find mnemonic context');
  assert.equal(form.get('stream'), 'false');
  assert.equal(form.get('ephemeral'), 'true');
  assert.equal(form.get('cgid'), '123');
  assert.equal(out.message, 'found');
});

test('goSearchResponse rejects empty semantic queries before any network call', async () => {
  let called = false;
  await assert.rejects(() => goSearchResponse({query:'   ', apiToken:'tok', fetchImpl:async()=>{called=true;}}), /query required/);
  assert.equal(called, false);
});

test('normalizeGoSearch marks output as discovery-only, never authoritative memory', () => {
  const out = normalizeGoSearch({completion:{message:'candidate'},conversationId:7});
  assert.equal(out.authority, 'candidate_discovery_only');
  assert.equal(out.authoritative_drive_refetch_required, true);
  assert.equal(out.message, 'candidate');
});

test('MCP exposes only status and semantic_discover', async () => {
  const rpc=createRpc({statusFn:async()=>({ok:true}),discoverFn:async()=>({message:'x'})});
  const out=await rpc({jsonrpc:'2.0',id:1,method:'tools/list'});
  assert.deepEqual(out.result.tools.map(t=>t.name),['gosearch_status','semantic_discover']);
});

test('semantic_discover delegates one bounded query and returns structured discovery output', async () => {
  let seen='';
  const rpc=createRpc({statusFn:async()=>({ok:true}),discoverFn:async a=>{seen=a.query;return {message:'candidate',authority:'candidate_discovery_only'};}});
  const out=await rpc({jsonrpc:'2.0',id:2,method:'tools/call',params:{name:'semantic_discover',arguments:{query:'find current mnemonic'}}});
  assert.equal(seen,'find current mnemonic');
  assert.equal(out.result.structuredContent.authority,'candidate_discovery_only');
  assert.equal(out.result.isError,false);
});
