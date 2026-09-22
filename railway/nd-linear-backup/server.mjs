import http from 'node:http';
import crypto from 'node:crypto';

const PORT=Number(process.env.PORT||3000);
const API_KEY=String(process.env.ND_LINEAR_API_KEY||'').trim();
const BRIDGE_KEY=String(process.env.ND_LINEAR_BRIDGE_TOKEN||'').trim();
const DEVMODE_TOKEN=String(process.env.ND_LINEAR_DEVMODE_PATH_TOKEN||'').trim();
const DEVMODE_PATH='/mcp/'+DEVMODE_TOKEN;
const MCP_URL='https://mcp.linear.app/mcp';
const GQL_URL='https://api.linear.app/graphql';

function safeEqual(a,b){
  const x=Buffer.from(String(a||'')),y=Buffer.from(String(b||''));
  return x.length===y.length && x.length>0 && crypto.timingSafeEqual(x,y);
}
function cleanError(e){
  let s=String(e?.message||e);
  if(API_KEY)s=s.replaceAll(API_KEY,'[REDACTED]');
  if(BRIDGE_KEY)s=s.replaceAll(BRIDGE_KEY,'[REDACTED]');
  if(DEVMODE_TOKEN)s=s.replaceAll(DEVMODE_TOKEN,'[REDACTED]');
  return s.slice(0,1200);
}
function parseMcp(raw){
  const vals=[];
  for(const line of String(raw||'').split(/\r?\n/)){
    if(!line.startsWith('data: ')) continue;
    try{vals.push(JSON.parse(line.slice(6)));}catch{}
  }
  if(vals.length)return vals[vals.length-1];
  try{return JSON.parse(String(raw||'{}'));}catch{return {raw:String(raw||'').slice(0,6000)};}
}
async function linearPost(payload,sid=null,timeoutMs=60000){
  if(!API_KEY)throw new Error('linear_not_configured');
  const headers={
    authorization:'Bearer '+API_KEY,
    'content-type':'application/json',
    accept:'application/json, text/event-stream',
    'user-agent':'ND-Linear-Backup/1.0'
  };
  if(sid){
    headers['mcp-session-id']=sid;
    headers['mcp-protocol-version']='2025-06-18';
  }
  const controller=new AbortController();
  const timer=setTimeout(()=>controller.abort(),timeoutMs);
  try{
    const r=await fetch(MCP_URL,{method:'POST',headers,body:JSON.stringify(payload),signal:controller.signal});
    const raw=await r.text();
    if(!r.ok)throw new Error('Linear MCP HTTP '+r.status+': '+raw.slice(0,900));
    return {status:r.status,sid:r.headers.get('mcp-session-id'),body:parseMcp(raw)};
  } finally {clearTimeout(timer);}
}
async function sessionCall(method,params={}){
  const init=await linearPost({
    jsonrpc:'2.0',id:1,method:'initialize',
    params:{protocolVersion:'2025-06-18',capabilities:{},clientInfo:{name:'ND Linear Backup',version:'1.0'}}
  });
  if(init.status!==200)throw new Error('linear_initialize_failed');
  await linearPost({jsonrpc:'2.0',method:'notifications/initialized',params:{}},init.sid);
  const call=await linearPost({jsonrpc:'2.0',id:2,method,params},init.sid);
  return {serverInfo:init.body?.result?.serverInfo||{},response:call.body};
}
function toolPayload(resp){
  const content=resp?.result?.content||[];
  for(const part of content){
    if(part?.type!=='text'||!part?.text)continue;
    try{return JSON.parse(part.text);}catch{}
  }
  return null;
}
async function gql(query,variables={}){
  if(!API_KEY)throw new Error('linear_not_configured');
  const r=await fetch(GQL_URL,{
    method:'POST',
    headers:{Authorization:API_KEY,'Content-Type':'application/json',Accept:'application/json','User-Agent':'ND-Linear-Backup-GraphQL/1.0'},
    body:JSON.stringify({query,variables})
  });
  const text=await r.text();
  if(!r.ok)throw new Error('Linear GraphQL HTTP '+r.status+': '+text.slice(0,900));
  const obj=JSON.parse(text||'{}');
  if(obj.errors?.length)throw new Error('Linear GraphQL errors: '+JSON.stringify(obj.errors).slice(0,1000));
  return obj.data||{};
}
async function gqlFallback(tool,args,primaryError){
  if(tool==='get_issue'){
    const id=String(args.id||args.issueId||'').trim();
    const d=await gql('query($id:String!){issue(id:$id){id identifier title description updatedAt state{id name type}}}',{id});
    return {transport:'linear_graphql_fallback',primary_error:cleanError(primaryError),result:d.issue||null};
  }
  if(tool==='list_comments'){
    const id=String(args.issueId||'').trim();
    const d=await gql('query($id:String!){issue(id:$id){id identifier comments(first:100){nodes{id body createdAt updatedAt}}}}',{id});
    const issue=d.issue||{};
    return {transport:'linear_graphql_fallback',primary_error:cleanError(primaryError),result:{issue_id:issue.id,identifier:issue.identifier,comments:issue.comments?.nodes||[]}};
  }
  if(tool==='save_comment'){
    const body=String(args.body||'');
    if(args.id){
      const d=await gql('mutation($id:String!,$body:String!){commentUpdate(id:$id,input:{body:$body}){success comment{id body updatedAt}}}',{id:String(args.id),body});
      return {transport:'linear_graphql_fallback',primary_error:cleanError(primaryError),result:d.commentUpdate};
    }
    const ref=String(args.issueId||'').trim();
    const d0=await gql('query($id:String!){issue(id:$id){id}}',{id:ref});
    const issueId=String(d0.issue?.id||'');
    if(!issueId)throw new Error('issue_not_found');
    const d=await gql('mutation($issueId:String!,$body:String!){commentCreate(input:{issueId:$issueId,body:$body}){success comment{id body updatedAt}}}',{issueId,body});
    return {transport:'linear_graphql_fallback',primary_error:cleanError(primaryError),result:d.commentCreate};
  }
  if(tool==='delete_comment'){
    const d=await gql('mutation($id:String!){commentDelete(id:$id){success}}',{id:String(args.id||'')});
    return {transport:'linear_graphql_fallback',primary_error:cleanError(primaryError),result:d.commentDelete};
  }
  if(tool==='save_issue' && args.id && !args.patch){
    const id=String(args.id);
    if('title' in args && 'description' in args){
      const d=await gql('mutation($id:String!,$title:String!,$description:String!){issueUpdate(id:$id,input:{title:$title,description:$description}){success issue{id identifier title description updatedAt}}}',{id,title:String(args.title||''),description:String(args.description||'')});
      return {transport:'linear_graphql_fallback',primary_error:cleanError(primaryError),result:d.issueUpdate};
    }
    if('description' in args){
      const d=await gql('mutation($id:String!,$description:String!){issueUpdate(id:$id,input:{description:$description}){success issue{id identifier title description updatedAt}}}',{id,description:String(args.description||'')});
      return {transport:'linear_graphql_fallback',primary_error:cleanError(primaryError),result:d.issueUpdate};
    }
    if('title' in args){
      const d=await gql('mutation($id:String!,$title:String!){issueUpdate(id:$id,input:{title:$title}){success issue{id identifier title description updatedAt}}}',{id,title:String(args.title||'')});
      return {transport:'linear_graphql_fallback',primary_error:cleanError(primaryError),result:d.issueUpdate};
    }
  }
  throw primaryError;
}
async function toolCall(tool,args={}){
  try{
    const r=await sessionCall('tools/call',{name:tool,arguments:args});
    return {transport:'official_linear_mcp',serverInfo:r.serverInfo,response:r.response};
  }catch(e){
    return gqlFallback(tool,args,e);
  }
}
async function health(){
  const tl=await sessionCall('tools/list',{});
  const tools=tl.response?.result?.tools||[];
  const ws=await sessionCall('tools/call',{name:'get_workspace',arguments:{}});
  const workspace=toolPayload(ws.response);
  return {
    ok:tools.length>0 && !!workspace,
    service:'ND Linear Backup',
    route:'dedicated_railway_official_linear_mcp',
    official_mcp:true,
    graphql_fallback:true,
    tools_count:tools.length,
    workspace_read:!!workspace,
    serverInfo:tl.serverInfo||ws.serverInfo||{}
  };
}
async function selftest(){
  const rec={schema:'nd-linear-backup-full-qualification-v1',ok:false};
  let commentId=null;
  const marker='ND Linear Backup qualification probe — safe to delete — '+new Date().toISOString();
  try{
    const tl=await sessionCall('tools/list',{});
    const tools=tl.response?.result?.tools||[];
    rec.tools_count=tools.length;
    rec.tools_catalog=tools.length>0;
    for(const name of ['get_workspace','get_issue','save_issue','save_document','save_project','save_comment','delete_comment','list_comments']){
      rec['has_'+name]=tools.some(x=>x?.name===name);
    }
    const issue=await toolCall('get_issue',{id:'NAM-122'});
    rec.issue_read=!!(issue.response ? toolPayload(issue.response) : issue.result);

    const wr=await toolCall('save_comment',{issueId:'NAM-122',body:marker});
    let created=wr.response ? (toolPayload(wr.response)||{}) : (wr.result?.comment||wr.result||{});
    commentId=String(created.id||'');
    rec.write=!!commentId;

    const rb=await toolCall('list_comments',{issueId:'NAM-122',limit:100});
    const listed=rb.response ? (toolPayload(rb.response)||{}) : (rb.result||{});
    rec.readback=!!commentId && (listed.comments||[]).some(x=>x?.id===commentId && x?.body===marker);

    if(commentId){
      const del=await toolCall('delete_comment',{id:commentId});
      const deleted=del.response ? (toolPayload(del.response)||{}) : (del.result||{});
      rec.delete=deleted.success===true || deleted.deleted===true;

      const rb2=await toolCall('list_comments',{issueId:'NAM-122',limit:100});
      const listed2=rb2.response ? (toolPayload(rb2.response)||{}) : (rb2.result||{});
      rec.cleanup_readback=!(listed2.comments||[]).some(x=>x?.id===commentId);
    }

    const required=['tools_catalog','has_get_workspace','has_get_issue','has_save_issue','has_save_document','has_save_project','has_save_comment','has_delete_comment','has_list_comments','issue_read','write','readback','delete','cleanup_readback'];
    rec.ok=required.every(k=>rec[k]===true);
  }catch(e){
    rec.error=cleanError(e);
    if(commentId){try{await toolCall('delete_comment',{id:commentId});rec.cleanup_after_error=true;}catch{}}
  }
  console.log(JSON.stringify({event:'ND_LINEAR_BACKUP_QUALIFICATION',...rec}));
  return rec;
}
function send(res,status,obj){
  const raw=Buffer.from(JSON.stringify(obj));
  res.writeHead(status,{'content-type':'application/json','content-length':String(raw.length),'cache-control':'no-store'});
  res.end(raw);
}
async function readJson(req){
  const chunks=[];for await(const c of req)chunks.push(c);
  return JSON.parse(Buffer.concat(chunks).toString('utf8')||'{}');
}
const server=http.createServer(async(req,res)=>{
  try{
    const path=(req.url||'/').split('?',1)[0];
    if(req.method==='GET'&&path==='/health'){
      try{return send(res,200,await health());}catch(e){return send(res,503,{ok:false,error:cleanError(e)});}
    }
    if(req.method==='POST'&&path==='/invoke'){
      const key=req.headers['x-nd-linear-key']||req.headers['x-nd-bridge-key'];
      if(!safeEqual(key,BRIDGE_KEY))return send(res,401,{ok:false,error:'unauthorized'});
      const body=await readJson(req);
      const op=String(body.operation||'');
      if(op==='tools_list'){
        const r=await sessionCall('tools/list',{});
        return send(res,200,{ok:true,provider:'linear',transport:'dedicated_railway_official_linear_mcp',serverInfo:r.serverInfo,response:r.response});
      }
      if(op==='tool_call'){
        const tool=String(body.tool||'').trim();
        if(!tool)return send(res,400,{ok:false,error:'tool_required'});
        const r=await toolCall(tool,body.arguments||{});
        return send(res,200,{ok:true,provider:'linear',...r});
      }
      return send(res,400,{ok:false,error:'operation_must_be_tools_list_or_tool_call'});
    }
    if(DEVMODE_TOKEN&&path===DEVMODE_PATH){
      if(req.method==='GET'){
        res.writeHead(200,{'content-type':'text/event-stream','cache-control':'no-store','connection':'keep-alive'});
        res.write(': nd-linear-backup\n\n');return res.end();
      }
      if(req.method!=='POST')return send(res,405,{ok:false,error:'method_not_allowed'});
      const msg=await readJson(req);
      const id=msg?.id??null,method=String(msg?.method||'');
      if(method==='initialize'){
        const init=await linearPost(msg);
        return send(res,200,init.body);
      }
      if(method==='ping')return send(res,200,{jsonrpc:'2.0',id,result:{}});
      if(method.startsWith('notifications/')){res.writeHead(202,{'cache-control':'no-store'});return res.end();}
      if(method==='tools/list'){
        const r=await sessionCall('tools/list',msg.params||{});
        const out=r.response||{};if(id!==null)out.id=id;return send(res,200,out);
      }
      if(method==='tools/call'){
        const tool=String(msg?.params?.name||'');
        const args=msg?.params?.arguments||{};
        const r=await toolCall(tool,args);
        if(r.response){const out=r.response;if(id!==null)out.id=id;return send(res,200,out);}
        return send(res,200,{jsonrpc:'2.0',id,result:{content:[{type:'text',text:JSON.stringify(r.result)}],structuredContent:r.result,isError:false}});
      }
      return send(res,200,{jsonrpc:'2.0',id,error:{code:-32601,message:'Method not found'}});
    }
    return send(res,404,{ok:false,error:'not_found'});
  }catch(e){return send(res,500,{ok:false,error:cleanError(e)});}
});
server.listen(PORT,'0.0.0.0',()=>{
  console.log(JSON.stringify({event:'ND_LINEAR_BACKUP_READY',port:PORT,configured:!!API_KEY,bridge_configured:!!BRIDGE_KEY,devmode_mcp_configured:!!DEVMODE_TOKEN}));
  setTimeout(()=>selftest().catch(e=>console.error(JSON.stringify({event:'ND_LINEAR_BACKUP_QUALIFICATION_CRASH',error:cleanError(e)}))),5000);
});
