import http from "node:http";

const PORT=Number(process.env.PORT||3000);
const TG_TOKEN=String(process.env.ND_TELEGRAM_PUBLISHER_BOT_TOKEN||"").trim();
const TG_CHANNEL=String(process.env.ND_TELEGRAM_CHANNEL_ID||"@NamelessDhamma").trim();
const PATH_TOKEN=String(process.env.ND_TELEGRAM_MCP_PATH_TOKEN||"").trim();
const WRITES=/^(1|true|yes|on)$/i.test(String(process.env.ND_TELEGRAM_WRITES_ENABLED||"false"));
const MCP_PATH=PATH_TOKEN?"/mcp/"+PATH_TOKEN:"";
const ND_TELEGRAM_HTTP_TIMEOUT_MS=Math.max(1000,Math.min(120000,Number(process.env.ND_TELEGRAM_HTTP_TIMEOUT_MS||30000)||30000));
const ND_TELEGRAM_MEDIA_TIMEOUT_MS=Math.max(5000,Math.min(300000,Number(process.env.ND_TELEGRAM_MEDIA_TIMEOUT_MS||120000)||120000));

const RO={readOnlyHint:true,destructiveHint:false,idempotentHint:true,openWorldHint:true};
const WR={readOnlyHint:false,destructiveHint:false,idempotentHint:false,openWorldHint:true};
const DEL={readOnlyHint:false,destructiveHint:true,idempotentHint:true,openWorldHint:true};

function j(res,status,obj){const body=JSON.stringify(obj);res.writeHead(status,{"content-type":"application/json; charset=utf-8","content-length":Buffer.byteLength(body)});res.end(body);}
async function body(req){const chunks=[];for await(const c of req)chunks.push(c);return chunks.length?Buffer.concat(chunks).toString("utf8"):"";}
function clean(e){let x=String(e?.message||e||"error");if(TG_TOKEN)x=x.split(TG_TOKEN).join("[REDACTED]");if(PATH_TOKEN)x=x.split(PATH_TOKEN).join("[REDACTED]");return x.slice(0,1800);}
async function tg(method,payload){
  if(!TG_TOKEN)throw new Error("telegram_token_missing");
  const timeoutMs=/^send(?:Video|Photo|Document|Audio|Animation)$/i.test(String(method||""))?ND_TELEGRAM_MEDIA_TIMEOUT_MS:ND_TELEGRAM_HTTP_TIMEOUT_MS;
  let r;
  try{
    r=await fetch("https://api.telegram.org/bot"+TG_TOKEN+"/"+method,{
      method:payload===undefined?"GET":"POST",
      headers:payload===undefined?{accept:"application/json"}:{"content-type":"application/json","accept":"application/json"},
      body:payload===undefined?undefined:JSON.stringify(payload),
      signal:AbortSignal.timeout(timeoutMs)
    });
  }catch(e){
    const n=String(e?.name||"");
    if(n==="TimeoutError"||n==="AbortError")throw new Error("telegram_http_timeout:"+timeoutMs);
    throw e;
  }
  const t=await r.text(); let o={}; try{o=t?JSON.parse(t):{};}catch{o={ok:false,description:t.slice(0,700)};}
  if(!r.ok||o.ok===false)throw new Error("telegram_http_"+r.status+":"+(o.description||"request_failed"));
  return o.result;
}

const TOOLS=[
 {name:"telegram_status",description:"Read publisher identity, target channel, publisher permissions, and bot administrators.",inputSchema:{type:"object",properties:{},additionalProperties:false},annotations:RO},
 {name:"telegram_send_text",description:"Publish text to the configured Nameless Dhamma Telegram channel.",inputSchema:{type:"object",properties:{text:{type:"string",minLength:1,maxLength:4096},disable_notification:{type:"boolean",default:false}},required:["text"],additionalProperties:false},annotations:WR},
 {name:"telegram_edit_text",description:"Edit a text message previously published by this bot.",inputSchema:{type:"object",properties:{message_id:{type:"integer",minimum:1},text:{type:"string",minLength:1,maxLength:4096}},required:["message_id","text"],additionalProperties:false},annotations:WR},
 {name:"telegram_delete_message",description:"Delete a Telegram channel message. Requires confirm=true.",inputSchema:{type:"object",properties:{message_id:{type:"integer",minimum:1},confirm:{type:"boolean"}},required:["message_id","confirm"],additionalProperties:false},annotations:DEL},
 {name:"telegram_send_photo",description:"Publish an image by HTTPS URL with optional caption.",inputSchema:{type:"object",properties:{photo_url:{type:"string",minLength:8},caption:{type:"string",maxLength:1024},disable_notification:{type:"boolean",default:false}},required:["photo_url"],additionalProperties:false},annotations:WR},
 {name:"telegram_send_video",description:"Publish a video by HTTPS URL with optional caption.",inputSchema:{type:"object",properties:{video_url:{type:"string",minLength:8},caption:{type:"string",maxLength:1024},disable_notification:{type:"boolean",default:false}},required:["video_url"],additionalProperties:false},annotations:WR}
];

async function status(){
  const me=await tg("getMe");
  const chat=await tg("getChat",{chat_id:TG_CHANNEL});
  const member=await tg("getChatMember",{chat_id:TG_CHANNEL,user_id:me.id});
  const admins=await tg("getChatAdministrators",{chat_id:TG_CHANNEL,return_bots:true});
  const adminBots=(admins||[]).filter(x=>x?.user?.is_bot).map(x=>({
    id:x.user.id,username:x.user.username||null,status:x.status,
    can_post_messages:x.can_post_messages??null,can_edit_messages:x.can_edit_messages??null,
    can_delete_messages:x.can_delete_messages??null,can_promote_members:x.can_promote_members??null
  }));
  return {ok:true,provider:"render-reserve",configured:Boolean(TG_TOKEN&&TG_CHANNEL&&PATH_TOKEN),writes:WRITES,
    bot:{id:me.id,username:me.username||null,is_bot:me.is_bot},
    channel:{id:chat.id,title:chat.title||null,username:chat.username||null,type:chat.type},
    membership:{status:member.status,can_manage_chat:member.can_manage_chat??null,can_post_messages:member.can_post_messages??null,
      can_edit_messages:member.can_edit_messages??null,can_delete_messages:member.can_delete_messages??null,
      can_promote_members:member.can_promote_members??null,can_invite_users:member.can_invite_users??null},
    admin_bots:adminBots,zen_sync_present:adminBots.some(x=>String(x.username||"").toLowerCase()==="zen_sync_bot")};
}

async function call(name,a={}){
  if(name==="telegram_status")return await status();
  if(!WRITES)throw new Error("telegram_writes_disabled");
  if(name==="telegram_send_text"){
    const m=await tg("sendMessage",{chat_id:TG_CHANNEL,text:String(a.text||""),disable_notification:Boolean(a.disable_notification)});
    return {ok:true,message:{message_id:m.message_id,date:m.date,chat_id:m.chat?.id,text:m.text||null}};
  }
  if(name==="telegram_edit_text"){
    const m=await tg("editMessageText",{chat_id:TG_CHANNEL,message_id:Number(a.message_id),text:String(a.text||"")});
    return {ok:true,message:{message_id:m.message_id,date:m.date,edit_date:m.edit_date,text:m.text||null}};
  }
  if(name==="telegram_delete_message"){
    if(a.confirm!==true)throw new Error("confirm_required");
    const out=await tg("deleteMessage",{chat_id:TG_CHANNEL,message_id:Number(a.message_id)});
    return {ok:Boolean(out),message_id:Number(a.message_id)};
  }
  if(name==="telegram_send_photo"){
    const m=await tg("sendPhoto",{chat_id:TG_CHANNEL,photo:String(a.photo_url||""),caption:a.caption===undefined?undefined:String(a.caption),disable_notification:Boolean(a.disable_notification)});
    return {ok:true,message:{message_id:m.message_id,date:m.date,chat_id:m.chat?.id,caption:m.caption||null}};
  }
  if(name==="telegram_send_video"){
    const m=await tg("sendVideo",{chat_id:TG_CHANNEL,video:String(a.video_url||""),caption:a.caption===undefined?undefined:String(a.caption),disable_notification:Boolean(a.disable_notification)});
    return {ok:true,message:{message_id:m.message_id,date:m.date,chat_id:m.chat?.id,caption:m.caption||null}};
  }
  throw new Error("unknown_tool");
}

async function mcp(req,res){
  let msg;try{msg=JSON.parse(await body(req)||"{}");}catch{return j(res,400,{jsonrpc:"2.0",id:null,error:{code:-32700,message:"parse error"}});}
  const id=msg.id,method=String(msg.method||"");
  if(method==="notifications/initialized"){res.writeHead(204);return res.end();}
  if(method==="initialize")return j(res,200,{jsonrpc:"2.0",id,result:{protocolVersion:"2025-06-18",capabilities:{tools:{listChanged:false}},serverInfo:{name:"nd-telegram-publisher-reserve",version:"1.0.0"},instructions:"Independent Render reserve for Nameless Dhamma Telegram publishing. Writes obey ND_TELEGRAM_WRITES_ENABLED; deletion requires confirm=true."}});
  if(method==="ping")return j(res,200,{jsonrpc:"2.0",id,result:{}});
  if(method==="tools/list")return j(res,200,{jsonrpc:"2.0",id,result:{tools:TOOLS}});
  if(method==="tools/call"){
    try{const out=await call(String(msg.params?.name||""),msg.params?.arguments||{});return j(res,200,{jsonrpc:"2.0",id,result:{content:[{type:"text",text:JSON.stringify(out)}],structuredContent:out,isError:false}});}
    catch(e){const out={ok:false,error:clean(e)};return j(res,200,{jsonrpc:"2.0",id,result:{content:[{type:"text",text:JSON.stringify(out)}],structuredContent:out,isError:true}});}
  }
  return j(res,200,{jsonrpc:"2.0",id,error:{code:-32601,message:"Method not found"}});
}

http.createServer(async(req,res)=>{
  const path=new URL(req.url,"http://localhost").pathname;
  if(path==="/healthz")return j(res,200,{ok:true,service:"nd-telegram-publisher-reserve",provider:"render",configured:Boolean(TG_TOKEN&&TG_CHANNEL&&PATH_TOKEN),writes:WRITES});
  if(MCP_PATH&&path===MCP_PATH){
    if(req.method==="GET")return j(res,200,{ok:true,service:"nd-telegram-publisher-reserve",transport:"streamable-http",tools:TOOLS.length,configured:Boolean(TG_TOKEN&&TG_CHANNEL),writes:WRITES});
    if(req.method==="POST")return await mcp(req,res);
    res.writeHead(405,{Allow:"GET, POST"});return res.end();
  }
  return j(res,404,{ok:false,error:"not_found"});
}).listen(PORT,()=>console.log(JSON.stringify({event:"started",service:"nd-telegram-publisher-reserve",port:PORT,configured:Boolean(TG_TOKEN&&TG_CHANNEL&&PATH_TOKEN),writes:WRITES})));