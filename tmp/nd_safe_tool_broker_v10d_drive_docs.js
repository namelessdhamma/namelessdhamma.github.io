console.log("ND_DRIVE_V10D_WRAPPER_START");\nconst BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/d519ae887c5d7a972b9dc676eef58c964cd6c6b0/tmp/nd_safe_tool_broker_v9_father_comment.js';
let outer=await (await fetch(BASE)).text();
const FRAG='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/719aaebd08ae3335df39b35e85d35cade4a09879/tmp/nd_drive_docs_v10.jsfrag';
const driveFrag=await (await fetch(FRAG)).text();
const finalizer="const encoded=Buffer.from(patched).toString('base64');";
if(!outer.includes(finalizer))throw new Error('v10c finalizer marker missing');

const inner=String.raw`
const ddInvoke='async function invokeTool(name,q,args={}){';
if(!patched.includes(ddInvoke))throw new Error('v10c runtime invoke marker missing');
patched=patched.replace(ddInvoke,driveFrag+"\n"+ddInvoke+
 'if(name==="docs_read")return await docsRead(args);'+
 'if(name==="docs_append")return await docsAppend(args);'+
 'if(name==="docs_replace_exact")return await docsReplaceExact(args);'+
 'if(name==="drive_get_metadata")return await driveMetadata(args);'+
 'if(name==="drive_get_currentness_token")return await currentnessToken(args);'+
 'if(name==="drive_changes_start_token")return await changesStartToken(args);'+
 'if(name==="drive_changes_list")return await changesList(args);');

const ddCat='TOOL_CATALOG.broker_executable.push(';
if(!patched.includes(ddCat))throw new Error('v10c runtime catalog marker missing');
patched=patched.replace(ddCat,ddCat+
 '{name:"docs_read",description:"Read Google Doc full text and revisionId."},'+
 '{name:"docs_append",description:"Revision-guarded append to allowlisted Google Doc."},'+
 '{name:"docs_replace_exact",description:"Revision-guarded exact replacement in allowlisted Google Doc."},'+
 '{name:"drive_get_metadata",description:"Read Drive version and modifiedTime metadata."},'+
 '{name:"drive_get_currentness_token",description:"Read Drive version/modifiedTime plus Docs revisionId."},'+
 '{name:"drive_changes_start_token",description:"Get Drive changes start token."},'+
 '{name:"drive_changes_list",description:"List Drive changes for reconciliation."},');

const ddServe='Bun.serve({port:PORT,fetch:handler});';
if(!patched.includes(ddServe))throw new Error('v10c runtime serve marker missing');
const probe=String.raw\`
console.log("ND_DRIVE_DOCS_V10_START",JSON.stringify({writable_ids:DRIVE_DOCS_WRITABLE.size,tools:7}));
setTimeout(async()=>{
 const id="1N_cYTm6zXXQXKTBAaPGq_eBt28tzhTB5HahCF8W-ZLc",t=Date.now();
 try{
  const d=await docsRead({document_id:id}),c=await currentnessToken({file_id:id});
  console.log("ND_DRIVE_DOCS_V10_PROBE",JSON.stringify({ok:true,elapsed_ms:Date.now()-t,title:d.title,revision_id:d.revision_id,text_chars:d.text.length,drive_version:c.drive_version,modified_time:c.modified_time,revision_match:c.docs_revision_id===d.revision_id}));
 }catch(e){console.error("ND_DRIVE_DOCS_V10_PROBE",JSON.stringify({ok:false,error:String(e).slice(0,500)}));}
},5000);
\`;
patched=patched.replace(ddServe,ddServe+"\n"+probe);
`;
const patchLogic='const driveFrag='+JSON.stringify(driveFrag)+';\n'+inner;
outer=outer.replace(finalizer,patchLogic+'\n'+finalizer);
console.log('ND_DRIVE_V10D_OUTER_READY',JSON.stringify({outer_chars:outer.length,has_patch_logic:outer.includes('v10c runtime invoke marker'),has_docs_read:outer.includes('docs_read')}));\nawait import('data:text/javascript;base64,'+Buffer.from(outer).toString('base64'));
