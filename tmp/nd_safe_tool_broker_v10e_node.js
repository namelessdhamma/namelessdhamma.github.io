import { Buffer } from "node:buffer";

const BASE="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/d519ae887c5d7a972b9dc676eef58c964cd6c6b0/tmp/nd_safe_tool_broker_v9_father_comment.js";
const FRAG="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/719aaebd08ae3335df39b35e85d35cade4a09879/tmp/nd_drive_docs_v10.jsfrag";
let outer=await (await fetch(BASE)).text();
const driveFrag=await (await fetch(FRAG)).text();
const finalizer="const encoded=Buffer.from(patched).toString('base64');";
if(!outer.includes(finalizer))throw new Error("v10e finalizer marker missing");

const patch=String.raw`
const ddInvoke='async function invokeTool(name,q,args={}){';
if(!patched.includes(ddInvoke))throw new Error('v10e invoke marker missing');
patched=patched.replace(ddInvoke,driveFrag+"\n"+ddInvoke+
 'if(name==="docs_read")return await docsRead(args);'+
 'if(name==="docs_append")return await docsAppend(args);'+
 'if(name==="docs_replace_exact")return await docsReplaceExact(args);'+
 'if(name==="drive_get_metadata")return await driveMetadata(args);'+
 'if(name==="drive_get_currentness_token")return await currentnessToken(args);'+
 'if(name==="drive_changes_start_token")return await changesStartToken(args);'+
 'if(name==="drive_changes_list")return await changesList(args);');

const serve='Bun.serve({port:PORT,fetch:handler});';
if(!patched.includes(serve))throw new Error('v10e Bun serve marker missing');
const nodeServe=String.raw\`
import { createServer } from "node:http";
const _ndServer=createServer(async(req,res)=>{
 try{
  const chunks=[];for await(const c of req)chunks.push(c);
  const body=chunks.length?Buffer.concat(chunks):undefined;
  const request=new Request("http://127.0.0.1:"+PORT+(req.url||"/"),{
   method:req.method,headers:req.headers,
   body:(req.method==="GET"||req.method==="HEAD")?undefined:body
  });
  const response=await handler(request);
  const headers={};response.headers.forEach((v,k)=>headers[k]=v);
  res.writeHead(response.status,headers);
  res.end(Buffer.from(await response.arrayBuffer()));
 }catch(e){console.error("ND_NODE_SHIM_ERROR",String(e).slice(0,500));res.writeHead(500,{"content-type":"application/json"});res.end(JSON.stringify({error:"internal"}));}
});
_ndServer.listen(PORT,"0.0.0.0",()=>console.log("ND_DRIVE_BROKER_NODE_READY",JSON.stringify({port:PORT,writable_ids:DRIVE_DOCS_WRITABLE.size,tools:7})));
\`;
patched=patched.replace(serve,nodeServe);
`;
outer=outer.replace(finalizer,"const driveFrag="+JSON.stringify(driveFrag)+";\n"+patch+"\n"+finalizer);
await import("data:text/javascript;base64,"+Buffer.from(outer).toString("base64"));
