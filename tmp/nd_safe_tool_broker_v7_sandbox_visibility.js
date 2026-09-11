const BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/aa7892ceb16b21bf7d2a514561c5dabb4a98cc39/tmp/nd_safe_tool_broker_v6_websearch_fallback.js';
let src=await (await fetch(BASE)).text();
const needle="const encoded=Buffer.from(patched).toString('base64');";
if(!src.includes(needle))throw new Error('V6 encode marker missing');
const probe=String.raw`setTimeout(async()=>{
  console.log("ND_SANDBOX_VISIBILITY_PROBE_START",JSON.stringify({mutations:false}));
  const ids=[
    ["root","1N7rXBuBg4Z8_35GXcjSC-F0snf37L0rL"],
    ["inbox","1LzNiq6PbE7yNZQqnHxexVbMkDpvI56Zl"],
    ["book_drafts","1aQ8cnGd423elt90t8vPjcPvp0x08oiFn"],
    ["research","1VksG2jZF6GjJUGPBspXwSTAtdQIx01S8"],
    ["outbox","1FfZS1jmrRF-BiCnzPnSqoD_2KHUzzGE8"],
    ["shared_notes","1cF1qB25BZPKmtvgoXXkSMrEh_LnYJiRD"]
  ];
  for(const [label,id] of ids){
    try{
      const m=await meta(id);
      console.log("ND_SANDBOX_VISIBILITY",JSON.stringify({label,id:m.id,name:m.name,mimeType:m.mimeType,parents:m.parents||[],visible:true,mutations:false}));
    }catch(e){
      console.error("ND_SANDBOX_VISIBILITY",JSON.stringify({label,id,visible:false,error:String(e).slice(0,300),mutations:false}));
    }
  }
},500);`;
const injected="const sandboxVisibilityProbe="+JSON.stringify(probe)+";\npatched=patched.replace(serveMarker,serveMarker+'\\n'+sandboxVisibilityProbe);\n"+needle;
src=src.replace(needle,injected);
const encoded=Buffer.from(src).toString('base64');
await import('data:text/javascript;base64,'+encoded);
