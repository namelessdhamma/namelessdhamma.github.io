import crypto from 'node:crypto';
import { driveMcpMessage } from '../drive_core.mjs';

function safeEqual(a,b){
  const x=Buffer.from(String(a||'')),y=Buffer.from(String(b||''));
  return x.length===y.length&&x.length>0&&crypto.timingSafeEqual(x,y);
}
function send(res,status,obj){
  res.status(status);
  res.setHeader('content-type','application/json');
  res.setHeader('cache-control','no-store');
  res.send(JSON.stringify(obj));
}
async function readJson(req){
  if(req.body&&typeof req.body==='object') return req.body;
  if(typeof req.body==='string') return JSON.parse(req.body||'{}');
  const chunks=[]; for await(const c of req) chunks.push(c);
  return JSON.parse(Buffer.concat(chunks).toString('utf8')||'{}');
}
export default async function handler(req,res){
  const bridge=String(process.env.ND_DRIVE_BRIDGE_TOKEN||'').trim();
  if(!safeEqual(req.headers['x-nd-bridge-key'],bridge)) return send(res,401,{ok:false,error:'unauthorized'});
  if(req.method==='GET'){
    res.statusCode=200;
    res.setHeader('content-type','text/event-stream');
    res.setHeader('cache-control','no-store');
    return res.end(': nd-drive-vercel\n\n');
  }
  if(req.method!=='POST') return send(res,405,{ok:false,error:'method_not_allowed'});
  try{
    const msg=await readJson(req);
    const out=await driveMcpMessage(msg);
    if(out===null){res.statusCode=202;return res.end();}
    return send(res,200,out);
  }catch(e){
    return send(res,400,{jsonrpc:'2.0',id:null,error:{code:-32700,message:String(e?.message||e).slice(0,500)}});
  }
}
