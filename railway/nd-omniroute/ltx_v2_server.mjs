import http from 'node:http';
import {createLtxMcpHandler,ltxHealth} from './ltx_mcp_v2.mjs';

const PORT=Number(process.env.PORT||8080);
const TOKEN=String(process.env.ND_LTX_MCP_PATH_TOKEN||'').trim();
const MCP_PATH='/ltx-mcp/'+TOKEN;
const handler=createLtxMcpHandler();

function json(res,status,obj){
  res.writeHead(status,{'content-type':'application/json','cache-control':'no-store','x-content-type-options':'nosniff'});
  res.end(JSON.stringify(obj));
}

const server=http.createServer(async (req,res)=>{
  try{
    const path=String(req.url||'').split('?')[0];
    if(req.method==='GET'&&path==='/healthz'){
      return json(res,200,{...(await ltxHealth()),service:'nd-ltx-control-v2',release:'NAM-397-v1'});
    }
    if(!TOKEN) return json(res,503,{ok:false,error:'ND_LTX_MCP_PATH_TOKEN_not_configured'});
    if(path===MCP_PATH){
      const handled=await handler(req,res);
      if(handled!==false) return;
    }
    return json(res,404,{ok:false,error:'not_found'});
  }catch(e){
    return json(res,503,{ok:false,error:String(e?.message||e).slice(0,800)});
  }
});

server.listen(PORT,'0.0.0.0',()=>{
  console.log(JSON.stringify({event:'ND_LTX_CONTROL_V2_LISTEN',port:PORT,release:'NAM-397-v1'}));
});
