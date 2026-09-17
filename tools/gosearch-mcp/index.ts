import { goSearchResponse } from './gosearch_core.mjs';
import { createRpc } from './mcp_core.mjs';

const FN='nd-gosearch-mcp';
const ROUTE_HASH='2e3d87e96ed7f837f1ede26c04c6346b992a8d1b834a97067c809467b7844ffe';
const GOSEARCH_API_TOKEN=Deno.env.get('GOSEARCH_API_TOKEN')||'';
const GOSEARCH_AGENT_CGID=Deno.env.get('GOSEARCH_AGENT_CGID')||'';

function cors(extra={}){return {'access-control-allow-origin':'*','access-control-allow-headers':'content-type, mcp-protocol-version','access-control-allow-methods':'GET,HEAD,POST,OPTIONS','cache-control':'no-store',...extra};}
function json(obj,status=200,extra={}){return new Response(JSON.stringify(obj),{status,headers:{'content-type':'application/json',...cors(extra)}});}
function text(body,status=200,extra={}){return new Response(body,{status,headers:{'content-type':'text/plain; charset=utf-8',...cors(extra)}});}
function hex(buf){return Array.from(new Uint8Array(buf)).map(x=>x.toString(16).padStart(2,'0')).join('');}
async function sha256(s){return hex(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(s)));}
function routeParts(req){const u=new URL(req.url);const parts=u.pathname.split('/').filter(Boolean);const i=parts.lastIndexOf(FN);if(i<0)return {token:'',tail:'/'};return {token:parts[i+1]||'',tail:'/'+parts.slice(i+2).join('/')};}
async function authorized(token){return token.length>=20 && (await sha256(token))===ROUTE_HASH;}

async function status(){return {ok:true,service:FN,provider:'gosearch',configured:Boolean(GOSEARCH_API_TOKEN),agent_cgid_configured:Boolean(GOSEARCH_AGENT_CGID),authority:'candidate_discovery_only',write_authority:false,canonical_memory:false,authoritative_drive_refetch_required:true,api:'https://api.gosearch.ai/goai/response'};}
async function discover(args){return await goSearchResponse({query:args?.query,apiToken:GOSEARCH_API_TOKEN,cgid:GOSEARCH_AGENT_CGID});}
const rpc=createRpc({statusFn:status,discoverFn:discover});

Deno.serve(async req=>{
  try{
    if(req.method==='OPTIONS')return new Response('',{status:204,headers:cors()});
    const {token,tail}=routeParts(req);
    if(tail==='/healthz' || (tail==='/' && !token))return json({ok:true,service:FN,configured:Boolean(GOSEARCH_API_TOKEN),mcp_auth:'opaque_path_token',write_authority:false});
    if(!(await authorized(token)))return text('Not found',404);
    if(tail==='/status' && req.method==='GET')return json(await status());
    if(tail!=='/mcp')return text('Not found',404);
    if(req.method!=='POST')return text('POST only',405);
    const msg=await req.json().catch(()=>null);if(!msg)return json({error:'invalid_json'},400);
    const out=await rpc(msg);if(!out)return new Response('',{status:202,headers:cors()});
    return json(out,200,{'mcp-protocol-version':String(msg.params?.protocolVersion||req.headers.get('mcp-protocol-version')||'2025-06-18')});
  }catch(e){console.error(e);return json({error:String(e?.message||e)},500);}
});
