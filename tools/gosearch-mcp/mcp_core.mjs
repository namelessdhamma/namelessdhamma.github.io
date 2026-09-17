export const TOOLS=[
  {name:'gosearch_status',description:'Check ND GoSearch semantic-discovery configuration. No provider call.',inputSchema:{type:'object',properties:{},additionalProperties:false}},
  {name:'semantic_discover',description:'Run a read-only semantic discovery query through GoSearch. Results are candidates only and require authoritative Google Drive re-fetch.',inputSchema:{type:'object',properties:{query:{type:'string',minLength:1,maxLength:30000}},required:['query'],additionalProperties:false}}
];

export function createRpc({statusFn,discoverFn}){
  return async function rpc(msg){
    const id=msg?.id;
    if(id===undefined||id===null) return null;
    try{
      if(msg.method==='initialize'){
        const pv=msg.params?.protocolVersion||'2025-06-18';
        return {jsonrpc:'2.0',id,result:{protocolVersion:pv,capabilities:{tools:{listChanged:false}},serverInfo:{name:'nd-gosearch-mcp',version:'0.1.0'},instructions:'Read-only semantic discovery. GoSearch output is candidate-only; authoritative/current context must be re-fetched from Google Drive.'}};
      }
      if(msg.method==='ping') return {jsonrpc:'2.0',id,result:{}};
      if(msg.method==='tools/list') return {jsonrpc:'2.0',id,result:{tools:TOOLS}};
      if(msg.method==='tools/call'){
        const name=String(msg.params?.name||'');
        const args=msg.params?.arguments||{};
        let out;
        if(name==='gosearch_status') out=await statusFn();
        else if(name==='semantic_discover') out=await discoverFn(args);
        else throw new Error('unknown tool');
        return {jsonrpc:'2.0',id,result:{content:[{type:'text',text:JSON.stringify(out,null,2)}],structuredContent:out,isError:false}};
      }
      return {jsonrpc:'2.0',id,error:{code:-32601,message:'Method not found'}};
    }catch(e){
      return {jsonrpc:'2.0',id,result:{content:[{type:'text',text:String(e?.message||e)}],isError:true}};
    }
  };
}
