import http from 'node:http';
import { Buffer } from 'node:buffer';
import { createHash } from 'node:crypto';

const PORT = Number(process.env.PORT || 3000);
const RPC_URL = process.env.RPC_URL || 'https://zkbmkhpyrddsiuynjgzd.supabase.co/functions/v1/nd-true-memory-webdav-rpc';
const ROOT = 'ND';

const MCP_URL = process.env.MCP_URL || 'https://zkbmkhpyrddsiuynjgzd.supabase.co/functions/v1/nd-true-memory-obsidian/mcp';

async function mcpCall(method, params={}) {
  const token = process.env.MCP_TOKEN || '';
  if (!token) throw new Error('MCP_TOKEN missing');
  const r = await fetch(MCP_URL,{
    method:'POST',
    headers:{
      'authorization':'Bearer '+token,
      'content-type':'application/json',
      'mcp-protocol-version':'2025-06-18'
    },
    body:JSON.stringify({jsonrpc:'2.0',id:1,method,params})
  });
  const data = await r.json();
  if (!r.ok) throw new Error('MCP HTTP '+r.status);
  return data;
}
async function callTool(name,args={}){
  const r=await mcpCall('tools/call',{name,arguments:args});
  if (r?.result?.isError) {
    const msg=r?.result?.content?.[0]?.text || 'tool error';
    throw new Error(msg);
  }
  return r?.result?.structuredContent || {};
}

async function runAndroidPullProbe(){
  if(process.env.ANDROID_PULL_PROBE!=='1') return;
  const stamp=Date.now();
  const path='ND Integration Tests/True Memory Android Pull Probe '+stamp+'.md';
  const out=await callTool('create_note',{
    path,
    content:'# True Memory Android pull probe\n\nmarker: '+stamp+'\nstatus: awaiting Android bidirectional pull\n'
  });
  console.log('ANDROID_PULL_PROBE_RESULT '+JSON.stringify({ok:true,path,etag:out.etag}));
}

async function runMcpQualification(){
  if(process.env.QUALIFY_MCP!=='1') return;
  const stamp=Date.now();
  const p1='ND Integration Tests/True Memory MCP Qualification '+stamp+'.md';
  const p2='ND Integration Tests/True Memory MCP Qualification '+stamp+' Renamed.md';
  const result={ok:false,steps:[]};
  let currentPath=p1, currentEtag='';
  try{
    const list=await mcpCall('tools/list',{});
    const names=(list?.result?.tools||[]).map(x=>x.name);
    result.steps.push({step:'tools_list',hasCreate:names.includes('create_note'),hasUpdate:names.includes('update_note'),hasRename:names.includes('rename_note'),hasDelete:names.includes('delete_note')});
    const c=await callTool('create_note',{path:p1,content:'# True Memory MCP qualification\n\nstage: create\n'});
    currentEtag=c.etag; result.steps.push({step:'create',ok:!!c.created});
    const r1=await callTool('read_note',{path:p1});
    currentEtag=r1.etag; result.steps.push({step:'read_after_create',ok:r1.path===p1});
    const u=await callTool('update_note',{path:p1,content:'# True Memory MCP qualification\n\nstage: update\n',expected_etag:currentEtag});
    currentEtag=u.etag; result.steps.push({step:'update',ok:!!u.updated});
    const r2=await callTool('read_note',{path:p1});
    currentEtag=r2.etag; result.steps.push({step:'read_after_update',ok:r2.content.includes('stage: update')});
    const rn=await callTool('rename_note',{path:p1,new_path:p2,expected_etag:currentEtag});
    currentPath=p2; currentEtag=rn.etag; result.steps.push({step:'rename',ok:!!rn.renamed});
    const r3=await callTool('read_note',{path:p2});
    currentEtag=r3.etag; result.steps.push({step:'read_after_rename',ok:r3.path===p2});
    const d=await callTool('delete_note',{path:p2,expected_etag:currentEtag});
    result.steps.push({step:'delete',ok:!!d.deleted});
    currentPath='';
    const miss=await mcpCall('tools/call',{name:'read_note',arguments:{path:p2}});
    const isErr=!!miss?.result?.isError;
    result.steps.push({step:'read_after_delete',ok:isErr});
    result.ok=result.steps.every(x=>x.ok!==false);
  }catch(e){
    result.error=String(e?.message||e);
    try{
      if(currentPath && currentEtag) await callTool('delete_note',{path:currentPath,expected_etag:currentEtag});
    }catch{}
  }
  console.log('MCP_QUALIFICATION_RESULT '+JSON.stringify(result));
}


function esc(s=''){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }
function authDigest(req){
  const h=req.headers.authorization||'';
  if(!h.startsWith('Basic ')) return null;
  try{
    const raw=Buffer.from(h.slice(6),'base64').toString('utf8');
    const i=raw.indexOf(':');
    if(i<1) return null;
    return createHash('sha256').update(raw,'utf8').digest('hex');
  }catch{return null;}
}
function baseHeaders(extra={}){
  return {
    'cache-control':'no-store',
    'DAV':'1,2',
    'Allow':'OPTIONS, PROPFIND, GET, HEAD, PUT, DELETE, MKCOL, MOVE',
    ...extra
  };
}
function send(res,status,body='',headers={}){
  res.writeHead(status,baseHeaders(headers));
  res.end(body);
}
function pathRel(urlString){
  const u=new URL(urlString,'http://local');
  const parts=u.pathname.split('/').filter(Boolean).map(decodeURIComponent);
  if(parts.length===0) return {ok:true,path:'',root:false};
  if(parts[0]!==ROOT) return {ok:false,path:'',root:false};
  return {ok:true,path:parts.slice(1).join('/'),root:true};
}
async function rpc(digest,op,payload={}){
  const r=await fetch(RPC_URL,{
    method:'POST',
    headers:{'content-type':'application/json','x-nd-webdav-digest':digest},
    body:JSON.stringify({op,...payload})
  });
  const text=await r.text();
  let data={};
  try{ data=text?JSON.parse(text):{}; }catch{ data={error:text||'invalid_json'}; }
  return {status:r.status,data};
}
function hrefFor(path,isDir){
  const seg=[ROOT,...String(path||'').split('/').filter(Boolean)].map(encodeURIComponent);
  return '/'+seg.join('/')+(isDir?'/':'');
}
function prop(item){
  const isDir=item.type==='directory';
  const href=hrefFor(item.path||'',isDir);
  const lm=new Date(item.updated_at||Date.now()).toUTCString();
  const len=isDir?0:Number(item.size||0);
  const et=isDir?'':`<d:getetag>&quot;${esc(item.etag||'')}&quot;</d:getetag>`;
  return `<d:response><d:href>${esc(href)}</d:href><d:propstat><d:prop><d:resourcetype>${isDir?'<d:collection/>':''}</d:resourcetype><d:getcontentlength>${len}</d:getcontentlength><d:getlastmodified>${esc(lm)}</d:getlastmodified>${et}</d:prop><d:status>HTTP/1.1 200 OK</d:status></d:propstat></d:response>`;
}
async function readBody(req){
  const chunks=[]; for await (const c of req) chunks.push(c);
  return Buffer.concat(chunks);
}

const server=http.createServer(async(req,res)=>{
  try{
    if(req.method==='GET' && req.url==='/healthz') return send(res,200,'ok',{'content-type':'text/plain; charset=utf-8'});
    if(req.method==='OPTIONS') return send(res,204,'');
    const digest=authDigest(req);
    if(!digest) return send(res,401,'Unauthorized',{'WWW-Authenticate':'Basic realm="ND True Memory WebDAV"'});

    const pr=pathRel(req.url||'/');
    if(!pr.ok) return send(res,404,'Not found');
    const path=pr.path;

    if(req.method==='PROPFIND'){
      const st=await rpc(digest,'stat',{path});
      if(st.status>=400 || !st.data.exists) return send(res,404,'Not found');
      const depth=String(req.headers.depth||'1').toLowerCase();
      let items=[{...st.data,path,type:st.data.type}];
      if(depth!=='0' && st.data.type==='directory'){
        const li=await rpc(digest,'list',{path});
        if(li.status>=400) return send(res,li.status,'Not found');
        items.push(...(li.data.items||[]));
      }
      const xml='<?xml version="1.0" encoding="utf-8"?><d:multistatus xmlns:d="DAV:">'+items.map(prop).join('')+'</d:multistatus>';
      return send(res,207,xml,{'content-type':'application/xml; charset=utf-8'});
    }

    if(req.method==='GET' || req.method==='HEAD'){
      const g=await rpc(digest,'get',{path});
      if(g.status>=400) return send(res,404,'Not found');
      const buf=Buffer.from(g.data.content_base64||'','base64');
      const h={'content-type':'application/octet-stream','content-length':String(buf.length),'etag':'"'+(g.data.etag||'')+'"','last-modified':new Date(g.data.updated_at||Date.now()).toUTCString()};
      if(req.method==='HEAD') return send(res,200,'',h);
      res.writeHead(200,baseHeaders(h)); res.end(buf); return;
    }

    if(req.method==='PUT'){
      const buf=await readBody(req);
      const r=await rpc(digest,'put',{path,content_base64:buf.toString('base64')});
      if(r.status>=400) return send(res,r.status,JSON.stringify(r.data),{'content-type':'application/json'});
      return send(res,201,'',{'etag':'"'+(r.data.etag||'')+'"'});
    }

    if(req.method==='MKCOL'){
      const r=await rpc(digest,'mkdir',{path});
      if(r.status>=400) return send(res,r.status,JSON.stringify(r.data),{'content-type':'application/json'});
      return send(res,201,'');
    }

    if(req.method==='DELETE'){
      const r=await rpc(digest,'delete',{path});
      if(r.status===404) return send(res,404,'Not found');
      if(r.status>=400) return send(res,r.status,JSON.stringify(r.data),{'content-type':'application/json'});
      return send(res,204,'');
    }

    if(req.method==='MOVE'){
      const destHeader=req.headers.destination;
      if(!destHeader) return send(res,400,'Destination required');
      const durl=new URL(String(destHeader),'http://local');
      const dp=pathRel(durl.pathname);
      if(!dp.ok) return send(res,400,'Bad destination');
      const r=await rpc(digest,'move',{path,dest:dp.path});
      if(r.status>=400) return send(res,r.status,JSON.stringify(r.data),{'content-type':'application/json'});
      return send(res,201,'');
    }

    return send(res,405,'Method not allowed');
  }catch(e){
    console.error(e);
    return send(res,500,'Internal Server Error');
  }
});

server.listen(PORT,'0.0.0.0',()=>{console.log('ND True Memory WebDAV listening on',PORT); runMcpQualification().catch(e=>console.error('MCP_QUALIFICATION_FATAL',String(e?.message||e))); runAndroidPullProbe().catch(e=>console.error('ANDROID_PULL_PROBE_FATAL',String(e?.message||e)));});
