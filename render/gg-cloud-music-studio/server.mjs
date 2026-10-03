import http from 'node:http';
import crypto from 'node:crypto';
import { createRemoteJWKSet, jwtVerify } from 'jose';

const PORT = Number(process.env.PORT || 10000);
const STUDIO_TOKEN = process.env.GG_STUDIO_TOKEN || '';
const TTL_MS = Number(process.env.GG_JOB_TTL_MS || 2 * 60 * 60 * 1000);
const MAX_BODY = Number(process.env.GG_MAX_BODY_BYTES || 80 * 1024 * 1024);
const ALLOWED_REPO = 'namelessdhamma/namelessdhamma.github.io';
const ALLOWED_REF = 'refs/heads/gg/cloud-music-worker-v1';
const ALLOWED_WORKFLOW = `${ALLOWED_REPO}/.github/workflows/gg-cloud-music-worker.yml@${ALLOWED_REF}`;
const OIDC_ISSUER = 'https://token.actions.githubusercontent.com';
const JWKS = createRemoteJWKSet(new URL(OIDC_ISSUER + '/.well-known/jwks'));

const jobs = new Map();

function now() { return Date.now(); }
function json(res, status, obj, extra = {}) {
  const body = Buffer.from(JSON.stringify(obj));
  res.writeHead(status, {'content-type':'application/json; charset=utf-8','content-length':String(body.length),'cache-control':'no-store',...extra});
  res.end(body);
}
function text(res, status, body) {
  const b = Buffer.from(body);
  res.writeHead(status, {'content-type':'text/plain; charset=utf-8','content-length':String(b.length),'cache-control':'no-store'});
  res.end(b);
}
async function readBody(req, limit = MAX_BODY) {
  const chunks=[]; let size=0;
  for await (const c of req) {
    size += c.length;
    if (size > limit) throw Object.assign(new Error('body too large'), {status:413});
    chunks.push(c);
  }
  return Buffer.concat(chunks);
}
async function readJson(req, limit) {
  const b = await readBody(req, limit);
  if (!b.length) return {};
  return JSON.parse(b.toString('utf8'));
}
function safeName(name) {
  if (typeof name !== 'string' || !/^[A-Za-z0-9._-]{1,160}$/.test(name)) throw new Error('invalid asset name');
  return name;
}
function jobView(j) {
  return {
    job_id:j.id, operation:j.operation, project_id:j.projectId,
    status:j.status, created_at:j.createdAt, updated_at:j.updatedAt,
    claimed_at:j.claimedAt || null, completed_at:j.completedAt || null,
    error:j.error || null,
    assets:[...j.assets.entries()].map(([name,a])=>({name,mime_type:a.mimeType,size:a.size,parts:a.parts.size})),
    artifacts:[...j.artifacts.entries()].map(([name,a])=>({name,mime_type:a.mimeType,size:a.data.length}))
  };
}
function requireStudio(req) {
  const h=req.headers.authorization || '';
  if (!STUDIO_TOKEN || h !== `Bearer ${STUDIO_TOKEN}`) throw Object.assign(new Error('unauthorized'), {status:401});
}
async function requireRunner(req) {
  const h=req.headers.authorization || '';
  const token=h.startsWith('Bearer ') ? h.slice(7) : '';
  if (!token) throw Object.assign(new Error('missing runner oidc token'), {status:401});
  const {payload} = await jwtVerify(token, JWKS, {issuer:OIDC_ISSUER, audience:'gg-cloud-studio'});
  if (payload.repository !== ALLOWED_REPO || payload.ref !== ALLOWED_REF || payload.job_workflow_ref !== ALLOWED_WORKFLOW) {
    throw Object.assign(new Error('runner identity not allowed'), {status:403});
  }
  return payload;
}
function getJob(id) {
  const j=jobs.get(id);
  if (!j) throw Object.assign(new Error('job not found'), {status:404});
  return j;
}
function toolList() {
  return [
    {name:'studio_submit',description:'Create a private ephemeral GG cloud-music job. After this returns, trigger the worker by committing the returned marker JSON to the returned marker path on branch gg/cloud-music-worker-v1.',inputSchema:{type:'object',properties:{operation:{type:'string',description:'probe | ardour_lua | ardour_batch | project_render | vocal_render'},project_id:{type:'string'},payload_json:{type:'string',description:'Private JSON payload as a string; never write it to the public worker repository.'}},required:['operation','payload_json'],additionalProperties:false}},
    {name:'studio_put_asset_chunk',description:'Attach one private binary input to a job in base64 chunks. Chunks are kept only in the relay until the worker consumes them.',inputSchema:{type:'object',properties:{job_id:{type:'string'},name:{type:'string'},mime_type:{type:'string'},part_index:{type:'integer',minimum:0},data_base64:{type:'string'}},required:['job_id','name','part_index','data_base64'],additionalProperties:false}},
    {name:'studio_status',description:'Read one private cloud-music job status and artifact metadata.',inputSchema:{type:'object',properties:{job_id:{type:'string'}},required:['job_id'],additionalProperties:false}},
    {name:'studio_get_result',description:'Read the structured JSON result of a completed cloud-music job.',inputSchema:{type:'object',properties:{job_id:{type:'string'}},required:['job_id'],additionalProperties:false}},
    {name:'studio_get_artifact_chunk',description:'Read a completed binary artifact as a bounded base64 chunk.',inputSchema:{type:'object',properties:{job_id:{type:'string'},name:{type:'string'},offset:{type:'integer',minimum:0},length:{type:'integer',minimum:1,maximum:524288}},required:['job_id','name','offset','length'],additionalProperties:false}},
    {name:'studio_discard',description:'Delete an ephemeral job, its private input assets and output artifacts.',inputSchema:{type:'object',properties:{job_id:{type:'string'}},required:['job_id'],additionalProperties:false}},
    {name:'studio_capabilities',description:'Describe the GG cloud studio execution surfaces, singer catalog and artifact model.',inputSchema:{type:'object',properties:{},additionalProperties:false}},
    {name:'studio_health',description:'Read relay health and protocol version.',inputSchema:{type:'object',properties:{},additionalProperties:false}}
  ];
}
async function callTool(name,args={}) {
  if (name === 'studio_health') return {ok:true,service:'gg-cloud-music-studio-relay',version:'0.2.0',jobs:jobs.size};
  if (name === 'studio_submit') {
    const id=crypto.randomUUID();
    const markerPath=`gg-cloud-jobs/${id}.json`;
    const j={id,operation:String(args.operation||''),projectId:String(args.project_id||''),payloadJson:String(args.payload_json||''),status:'queued',createdAt:new Date().toISOString(),updatedAt:new Date().toISOString(),claimedAt:null,completedAt:null,error:null,resultJson:null,assets:new Map(),artifacts:new Map()};
    jobs.set(id,j);
    return {job_id:id,status:j.status,worker_branch:'gg/cloud-music-worker-v1',marker_path:markerPath,marker_json:JSON.stringify({job_id:id})};
  }
  const j=getJob(String(args.job_id||''));
  if (name === 'studio_put_asset_chunk') {
    if (!['queued','running'].includes(j.status)) throw new Error('job is not accepting assets');
    const n=safeName(args.name);
    const idx=Number(args.part_index);
    const data=Buffer.from(String(args.data_base64||''),'base64');
    let a=j.assets.get(n);
    if(!a){a={mimeType:String(args.mime_type||'application/octet-stream'),parts:new Map(),size:0};j.assets.set(n,a);}
    const prev=a.parts.get(idx); if(prev) a.size-=prev.length;
    a.parts.set(idx,data); a.size+=data.length; j.updatedAt=new Date().toISOString();
    return {ok:true,name:n,part_index:idx,part_size:data.length,total_size:a.size};
  }
  if (name === 'studio_status') return jobView(j);
  if (name === 'studio_get_result') return {job_id:j.id,status:j.status,result_json:j.resultJson,error:j.error,artifacts:jobView(j).artifacts};
  if (name === 'studio_get_artifact_chunk') {
    const n=safeName(args.name); const a=j.artifacts.get(n); if(!a) throw new Error('artifact not found');
    const off=Number(args.offset); const len=Math.min(Number(args.length),524288);
    const chunk=a.data.subarray(off,Math.min(a.data.length,off+len));
    return {job_id:j.id,name:n,mime_type:a.mimeType,offset:off,length:chunk.length,total_size:a.data.length,data_base64:chunk.toString('base64'),eof:off+chunk.length>=a.data.length};
  }
  if (name === 'studio_discard') { jobs.delete(j.id); return {ok:true,job_id:j.id}; }
  throw new Error('unknown tool');
}
async function mcp(req,res) {
  requireStudio(req);
  const msg=await readJson(req,8*1024*1024);
  if (msg.method === 'initialize') return json(res,200,{jsonrpc:'2.0',id:msg.id,result:{protocolVersion:'2025-03-26',capabilities:{tools:{}},serverInfo:{name:'gg-cloud-music-studio',version:'0.2.0'}}});
  if (msg.method === 'notifications/initialized') { res.writeHead(202); return res.end(); }
  if (msg.method === 'tools/list') return json(res,200,{jsonrpc:'2.0',id:msg.id,result:{tools:toolList()}});
  if (msg.method === 'tools/call') {
    try {
      const out=await callTool(msg.params?.name,msg.params?.arguments||{});
      return json(res,200,{jsonrpc:'2.0',id:msg.id,result:{content:[{type:'text',text:JSON.stringify(out)}],isError:false}});
    } catch(e) {
      return json(res,200,{jsonrpc:'2.0',id:msg.id,result:{content:[{type:'text',text:JSON.stringify({error:e.message})}],isError:true}});
    }
  }
  return json(res,200,{jsonrpc:'2.0',id:msg.id??null,error:{code:-32601,message:'method not found'}});
}
async function runnerRoute(req,res,url) {
  await requireRunner(req);
  const parts=url.pathname.split('/').filter(Boolean);
  const kind=parts[1], id=parts[2];
  if (kind === 'bootstrap' && req.method === 'POST') {
    const body=await readJson(req,256*1024);
    const operation=String(body.operation||'');
    if (!['probe','ardour_lua','ardour_batch','project_render','vocal_render'].includes(operation)) throw Object.assign(new Error('bootstrap operation not allowed'),{status:400});
    const jid=crypto.randomUUID();
    const payloadJson=typeof body.payload_json==='string' ? body.payload_json : JSON.stringify(body.payload||{});
    const j={id:jid,operation,projectId:'GG-STUDIO-SELFTEST',payloadJson,status:'queued',createdAt:new Date().toISOString(),updatedAt:new Date().toISOString(),claimedAt:null,completedAt:null,error:null,resultJson:null,assets:new Map(),artifacts:new Map()};
    jobs.set(jid,j);
    return json(res,200,{job_id:jid,status:j.status});
  }
  const j=getJob(id);
  if (kind === 'claim' && req.method === 'GET') {
    if (j.status === 'queued') { j.status='running'; j.claimedAt=new Date().toISOString(); j.updatedAt=j.claimedAt; }
    return json(res,200,{job_id:j.id,operation:j.operation,project_id:j.projectId,payload_json:j.payloadJson,assets:[...j.assets.entries()].map(([name,a])=>({name,mime_type:a.mimeType,size:a.size,parts:a.parts.size}))});
  }
  if (kind === 'asset' && req.method === 'GET') {
    const name=safeName(decodeURIComponent(parts.slice(3).join('/')));
    const a=j.assets.get(name); if(!a) return text(res,404,'asset not found');
    const data=Buffer.concat([...a.parts.entries()].sort((x,y)=>x[0]-y[0]).map(x=>x[1]));
    res.writeHead(200,{'content-type':a.mimeType,'content-length':String(data.length),'cache-control':'no-store'}); return res.end(data);
  }
  if (kind === 'artifact' && req.method === 'POST') {
    const name=safeName(decodeURIComponent(parts.slice(3).join('/')));
    const data=await readBody(req,MAX_BODY);
    j.artifacts.set(name,{mimeType:String(req.headers['content-type']||'application/octet-stream'),data});
    j.updatedAt=new Date().toISOString();
    return json(res,200,{ok:true,name,size:data.length});
  }
  if (kind === 'result' && req.method === 'POST') {
    const body=await readJson(req,8*1024*1024);
    j.status=body.ok ? 'completed' : 'failed';
    j.resultJson=typeof body.result_json==='string'?body.result_json:JSON.stringify(body.result_json??null);
    j.error=body.error?String(body.error):null;
    j.completedAt=new Date().toISOString(); j.updatedAt=j.completedAt;
    return json(res,200,{ok:true,status:j.status,artifacts:jobView(j).artifacts});
  }
  return text(res,404,'not found');
}
setInterval(()=>{
  const t=now();
  for(const [id,j] of jobs){
    if(t-Date.parse(j.updatedAt)>TTL_MS) jobs.delete(id);
  }
},300000).unref();

const server=http.createServer(async(req,res)=>{
  try{
    const url=new URL(req.url||'/',`http://${req.headers.host||'localhost'}`);
    if(url.pathname==='/health') return json(res,200,{ok:true,service:'gg-cloud-music-studio-relay',version:'0.2.0',jobs:jobs.size});
    if(url.pathname==='/mcp' && req.method==='POST') return await mcp(req,res);
    if(url.pathname.startsWith('/runner/')) return await runnerRoute(req,res,url);
    return text(res,404,'not found');
  }catch(e){
    const status=e.status||500;
    return json(res,status,{ok:false,error:e.message});
  }
});
server.listen(PORT,'0.0.0.0',()=>console.log(`gg-cloud-music-studio-relay listening on ${PORT}`));
