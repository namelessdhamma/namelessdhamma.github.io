const {createServer}=require("node:http");
const {spawn}=require("node:child_process");
const {writeFile}=require("node:fs/promises");

const PORT=Number(process.env.N8N_PORT||process.env.PORT||5678);
const PATH_TOKEN=String(process.env.ND_YOUTUBE_MCP_PATH_TOKEN||"").trim();
const CLIENT_ID=String(process.env.ND_YOUTUBE_CLIENT_ID||"").trim();
const CLIENT_SECRET=String(process.env.ND_YOUTUBE_CLIENT_SECRET||"").trim();
const REFRESH_TOKEN=String(process.env.ND_YOUTUBE_REFRESH_TOKEN||"").trim();
const WRITES=/^(1|true|yes|on)$/i.test(String(process.env.ND_SOCIAL_WRITES_ENABLED||"true"));
const GITHUB_PAT=String(process.env.ND_GITHUB_PAT||"").trim();
const MCP_PATH=PATH_TOKEN?"/nd/youtube/mcp/"+PATH_TOKEN:"";

function j(res,status,obj){
  const raw=Buffer.from(JSON.stringify(obj));
  res.writeHead(status,{"content-type":"application/json; charset=utf-8","content-length":String(raw.length),"cache-control":"no-store"});
  res.end(raw);
}
function cleanErr(e){
  let s=String(e?.message||e||"error");
  for(const v of [CLIENT_ID,CLIENT_SECRET,REFRESH_TOKEN,PATH_TOKEN,GITHUB_PAT]) if(v)s=s.split(v).join("[REDACTED]");
  return s.slice(0,1800);
}
async function accessToken(){
  if(!CLIENT_ID||!CLIENT_SECRET||!REFRESH_TOKEN)throw new Error("youtube_credentials_missing");
  const body=new URLSearchParams({client_id:CLIENT_ID,client_secret:CLIENT_SECRET,refresh_token:REFRESH_TOKEN,grant_type:"refresh_token"});
  const r=await fetch("https://oauth2.googleapis.com/token",{method:"POST",headers:{"content-type":"application/x-www-form-urlencoded"},body});
  const t=await r.text(); if(!r.ok)throw new Error("youtube_token_http_"+r.status+":"+t.slice(0,700));
  const o=JSON.parse(t); if(!o.access_token)throw new Error("youtube_access_token_missing"); return o.access_token;
}
async function yfetch(method,url,body){
  const token=await accessToken();
  const init={method,headers:{authorization:"Bearer "+token,accept:"application/json"}};
  if(body!==undefined){init.headers["content-type"]="application/json; charset=utf-8";init.body=JSON.stringify(body);}
  const r=await fetch(url,init); const t=await r.text();
  if(!r.ok)throw new Error("youtube_http_"+r.status+":"+t.slice(0,1400));
  return t?JSON.parse(t):{ok:true};
}
async function yapi(method,resource,query={},body){
  const clean=String(resource||"").replace(/^\/+/,"");
  if(!clean||clean.includes("..")||clean.includes("://"))throw new Error("invalid_youtube_resource");
  const u=new URL("https://www.googleapis.com/youtube/v3/"+clean);
  for(const [k,v] of Object.entries(query||{})){if(v!==undefined&&v!==null)u.searchParams.set(k,String(v));}
  return await yfetch(method,u.toString(),body);
}
async function channel(){
  const o=await yapi("GET","channels",{part:"id,snippet,statistics,contentDetails,brandingSettings,status",mine:"true",maxResults:"10"});
  const item=o.items?.[0]; if(!item)throw new Error("youtube_authorized_channel_not_found"); return item;
}
async function video(id){
  const o=await yapi("GET","videos",{part:"id,snippet,status,statistics,contentDetails",id});
  const item=o.items?.[0]; if(!item)throw new Error("youtube_video_not_found"); return item;
}
async function uploadFromUrl(a){
  if(!WRITES)throw new Error("youtube_writes_disabled");
  const src=await fetch(String(a.media_url||"")); if(!src.ok)throw new Error("media_fetch_http_"+src.status);
  const len=src.headers.get("content-length"); if(!len)throw new Error("media_content_length_required");
  const ctype=(src.headers.get("content-type")||"application/octet-stream").split(";")[0];
  const token=await accessToken();
  const snippet={title:String(a.title||""),description:String(a.description||""),categoryId:String(a.category_id||"22")};
  if(Array.isArray(a.tags)&&a.tags.length)snippet.tags=a.tags.map(String);
  const status={privacyStatus:String(a.privacy_status||"private"),selfDeclaredMadeForKids:Boolean(a.made_for_kids)};
  if(a.publish_at){status.privacyStatus="private";status.publishAt=String(a.publish_at);}
  const init=await fetch("https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status",{
    method:"POST",
    headers:{authorization:"Bearer "+token,"content-type":"application/json; charset=UTF-8","x-upload-content-type":ctype,"x-upload-content-length":len},
    body:JSON.stringify({snippet,status})
  });
  const initText=await init.text(); if(!init.ok)throw new Error("youtube_upload_init_"+init.status+":"+initText.slice(0,900));
  const loc=init.headers.get("location"); if(!loc)throw new Error("youtube_upload_session_missing");
  const put=await fetch(loc,{method:"PUT",headers:{authorization:"Bearer "+token,"content-type":ctype,"content-length":len},body:src.body,duplex:"half"});
  const out=await put.text(); if(!put.ok)throw new Error("youtube_upload_"+put.status+":"+out.slice(0,1200));
  return JSON.parse(out||"{}");
}
async function thumbnail(a){
  if(!WRITES)throw new Error("youtube_writes_disabled");
  const src=await fetch(String(a.image_url||"")); if(!src.ok)throw new Error("image_fetch_http_"+src.status);
  const buf=Buffer.from(await src.arrayBuffer()); if(buf.length>20*1024*1024)throw new Error("thumbnail_too_large");
  const token=await accessToken(); const u=new URL("https://www.googleapis.com/upload/youtube/v3/thumbnails/set");u.searchParams.set("videoId",String(a.video_id||""));
  const r=await fetch(u,{method:"POST",headers:{authorization:"Bearer "+token,"content-type":src.headers.get("content-type")||"application/octet-stream"},body:buf});
  const t=await r.text();if(!r.ok)throw new Error("youtube_thumbnail_"+r.status+":"+t.slice(0,1000));return JSON.parse(t||"{}");
}
const TOOLS=[
  ["youtube_account","Read authorized channel identity, handle, statistics and uploads playlist",{}],
  ["youtube_list_videos","List videos from the authorized channel uploads playlist",{max_results:{type:"integer"},page_token:{type:"string"}}],
  ["youtube_get_video","Read metadata, status and statistics for one video",{video_id:{type:"string"}}],
  ["youtube_update_video","Update title, description, tags, category, privacy, schedule or made-for-kids status",{video_id:{type:"string"},title:{type:"string"},description:{type:"string"},tags:{type:"array",items:{type:"string"}},category_id:{type:"string"},privacy_status:{type:"string"},publish_at:{type:"string"},made_for_kids:{type:"boolean"}}],
  ["youtube_delete_video","Permanently delete a video; confirm=true required",{video_id:{type:"string"},confirm:{type:"boolean"}}],
  ["youtube_upload_video_from_url","Upload a video from an HTTP(S) URL",{media_url:{type:"string"},title:{type:"string"},description:{type:"string"},privacy_status:{type:"string"},tags:{type:"array",items:{type:"string"}},category_id:{type:"string"},publish_at:{type:"string"},made_for_kids:{type:"boolean"}}],
  ["youtube_set_thumbnail","Set a custom thumbnail from an HTTP(S) URL",{video_id:{type:"string"},image_url:{type:"string"}}],
  ["youtube_list_comments","List comment threads for a video",{video_id:{type:"string"},max_results:{type:"integer"},page_token:{type:"string"}}],
  ["youtube_create_comment","Create a top-level comment",{video_id:{type:"string"},text:{type:"string"}}],
  ["youtube_reply_comment","Reply to a comment",{parent_comment_id:{type:"string"},text:{type:"string"}}],
  ["youtube_delete_comment","Delete a comment; confirm=true required",{comment_id:{type:"string"},confirm:{type:"boolean"}}],
  ["youtube_list_playlists","List playlists owned by the channel",{max_results:{type:"integer"},page_token:{type:"string"}}],
  ["youtube_create_playlist","Create a playlist",{title:{type:"string"},description:{type:"string"},privacy_status:{type:"string"}}],
  ["youtube_delete_playlist","Delete a playlist; confirm=true required",{playlist_id:{type:"string"},confirm:{type:"boolean"}}],
  ["youtube_add_to_playlist","Add a video to a playlist",{playlist_id:{type:"string"},video_id:{type:"string"},position:{type:"integer"}}],
  ["youtube_remove_from_playlist","Remove a playlist item; confirm=true required",{playlist_item_id:{type:"string"},confirm:{type:"boolean"}}],
  ["youtube_analytics","Query YouTube Analytics",{start_date:{type:"string"},end_date:{type:"string"},metrics:{type:"string"},dimensions:{type:"string"},filters:{type:"string"},sort:{type:"string"}}],
  ["youtube_api","Low-level full YouTube Data API v3 access",{method:{type:"string"},resource:{type:"string"},query:{type:"object"},body:{type:"object"},confirm_destructive:{type:"boolean"}}]
].map(([name,description,properties])=>({name,description,inputSchema:{type:"object",properties,additionalProperties:false}}));

async function callTool(name,a={}){
  if(name==="youtube_account"){const x=await channel(),s=x.snippet||{},st=x.statistics||{},cd=x.contentDetails||{};return {ok:true,channel:{id:x.id,title:s.title,customUrl:s.customUrl,description:s.description,subscriberCount:st.subscriberCount,videoCount:st.videoCount,viewCount:st.viewCount,uploadsPlaylist:cd.relatedPlaylists?.uploads}};}
  if(name==="youtube_list_videos"){const x=await channel(),id=x.contentDetails?.relatedPlaylists?.uploads;return {ok:true,result:await yapi("GET","playlistItems",{part:"id,snippet,contentDetails,status",playlistId:id,maxResults:Math.max(1,Math.min(Number(a.max_results||25),50)),...(a.page_token?{pageToken:a.page_token}:{})})};}
  if(name==="youtube_get_video")return {ok:true,result:await video(String(a.video_id||""))};
  if(name==="youtube_update_video"){if(!WRITES)throw new Error("youtube_writes_disabled");const id=String(a.video_id||""),x=await video(id),sn={...(x.snippet||{})},st={...(x.status||{})};if(a.title!==undefined)sn.title=String(a.title);if(a.description!==undefined)sn.description=String(a.description);if(a.tags!==undefined)sn.tags=(a.tags||[]).map(String);if(a.category_id)sn.categoryId=String(a.category_id);if(a.privacy_status)st.privacyStatus=String(a.privacy_status);if(a.publish_at){st.publishAt=String(a.publish_at);st.privacyStatus="private";}if(a.made_for_kids!==undefined)st.selfDeclaredMadeForKids=Boolean(a.made_for_kids);return {ok:true,result:await yapi("PUT","videos",{part:"snippet,status"},{id,snippet:sn,status:st})};}
  if(name==="youtube_delete_video"){if(!WRITES)throw new Error("youtube_writes_disabled");if(a.confirm!==true)throw new Error("confirm_required");return {ok:true,result:await yapi("DELETE","videos",{id:String(a.video_id||"")})};}
  if(name==="youtube_upload_video_from_url")return {ok:true,result:await uploadFromUrl(a)};
  if(name==="youtube_set_thumbnail")return {ok:true,result:await thumbnail(a)};
  if(name==="youtube_list_comments")return {ok:true,result:await yapi("GET","commentThreads",{part:"id,snippet,replies",videoId:String(a.video_id||""),maxResults:Math.max(1,Math.min(Number(a.max_results||50),100)),textFormat:"plainText",...(a.page_token?{pageToken:a.page_token}:{})})};
  if(name==="youtube_create_comment"){if(!WRITES)throw new Error("youtube_writes_disabled");return {ok:true,result:await yapi("POST","commentThreads",{part:"snippet"},{snippet:{videoId:String(a.video_id||""),topLevelComment:{snippet:{textOriginal:String(a.text||"")}}}})};}
  if(name==="youtube_reply_comment"){if(!WRITES)throw new Error("youtube_writes_disabled");return {ok:true,result:await yapi("POST","comments",{part:"snippet"},{snippet:{parentId:String(a.parent_comment_id||""),textOriginal:String(a.text||"")}})};}
  if(name==="youtube_delete_comment"){if(!WRITES)throw new Error("youtube_writes_disabled");if(a.confirm!==true)throw new Error("confirm_required");return {ok:true,result:await yapi("DELETE","comments",{id:String(a.comment_id||"")})};}
  if(name==="youtube_list_playlists")return {ok:true,result:await yapi("GET","playlists",{part:"id,snippet,status,contentDetails",mine:"true",maxResults:Math.max(1,Math.min(Number(a.max_results||50),50)),...(a.page_token?{pageToken:a.page_token}:{})})};
  if(name==="youtube_create_playlist"){if(!WRITES)throw new Error("youtube_writes_disabled");return {ok:true,result:await yapi("POST","playlists",{part:"snippet,status"},{snippet:{title:String(a.title||""),description:String(a.description||"")},status:{privacyStatus:String(a.privacy_status||"private")}})};}
  if(name==="youtube_delete_playlist"){if(!WRITES)throw new Error("youtube_writes_disabled");if(a.confirm!==true)throw new Error("confirm_required");return {ok:true,result:await yapi("DELETE","playlists",{id:String(a.playlist_id||"")})};}
  if(name==="youtube_add_to_playlist"){if(!WRITES)throw new Error("youtube_writes_disabled");const sn={playlistId:String(a.playlist_id||""),resourceId:{kind:"youtube#video",videoId:String(a.video_id||"")}};if(Number(a.position)>=0)sn.position=Number(a.position);return {ok:true,result:await yapi("POST","playlistItems",{part:"snippet"},{snippet:sn})};}
  if(name==="youtube_remove_from_playlist"){if(!WRITES)throw new Error("youtube_writes_disabled");if(a.confirm!==true)throw new Error("confirm_required");return {ok:true,result:await yapi("DELETE","playlistItems",{id:String(a.playlist_item_id||"")})};}
  if(name==="youtube_analytics"){const q={ids:"channel==MINE",startDate:String(a.start_date||""),endDate:String(a.end_date||""),metrics:String(a.metrics||"views,estimatedMinutesWatched,averageViewDuration,subscribersGained,subscribersLost")};for(const k of ["dimensions","filters","sort"])if(a[k])q[k]=String(a[k]);const u=new URL("https://youtubeanalytics.googleapis.com/v2/reports");for(const[k,v]of Object.entries(q))u.searchParams.set(k,v);return {ok:true,result:await yfetch("GET",u.toString())};}
  if(name==="youtube_api"){const m=String(a.method||"GET").toUpperCase();if(!["GET","POST","PUT","PATCH","DELETE"].includes(m))throw new Error("unsupported_http_method");if(m!=="GET"&&!WRITES)throw new Error("youtube_writes_disabled");if(m==="DELETE"&&a.confirm_destructive!==true)throw new Error("confirm_required");return {ok:true,result:await yapi(m,String(a.resource||""),a.query||{},["GET","DELETE"].includes(m)?undefined:(a.body||{}))};}
  throw new Error("unknown_tool");
}

async function readBody(req){const chunks=[];for await(const c of req)chunks.push(c);return chunks.length?Buffer.concat(chunks).toString("utf8"):"";}
async function mcp(req,res){
  let msg;try{msg=JSON.parse(await readBody(req)||"{}");}catch{return j(res,400,{jsonrpc:"2.0",id:null,error:{code:-32700,message:"parse error"}});}
  const id=msg.id,method=String(msg.method||"");
  if(method==="notifications/initialized"){res.writeHead(204);return res.end();}
  if(method==="initialize")return j(res,200,{jsonrpc:"2.0",id,result:{protocolVersion:"2025-06-18",capabilities:{tools:{}},serverInfo:{name:"nd-youtube-full-mcp",version:"1.0.0"},instructions:"Nameless Dhamma YouTube MCP with full read/write access. Destructive deletes require explicit confirm=true."}});
  if(method==="ping")return j(res,200,{jsonrpc:"2.0",id,result:{}});
  if(method==="tools/list")return j(res,200,{jsonrpc:"2.0",id,result:{tools:TOOLS}});
  if(method==="tools/call"){const p=msg.params||{};try{const out=await callTool(String(p.name||""),p.arguments||{});return j(res,200,{jsonrpc:"2.0",id,result:{content:[{type:"text",text:JSON.stringify(out)}],structuredContent:out,isError:false}});}catch(e){const out={ok:false,error:cleanErr(e)};return j(res,200,{jsonrpc:"2.0",id,result:{content:[{type:"text",text:JSON.stringify(out)}],structuredContent:out,isError:true}});}}
  return j(res,200,{jsonrpc:"2.0",id,error:{code:-32601,message:"Method not found"}});
}
async function health(){try{const x=await channel(),s=x.snippet||{},st=x.statistics||{};return {ok:true,service:"nd-youtube-full-mcp",read_write:WRITES,channel:{id:x.id,title:s.title,customUrl:s.customUrl,subscriberCount:st.subscriberCount,videoCount:st.videoCount,viewCount:st.viewCount}};}catch(e){return {ok:false,service:"nd-youtube-full-mcp",error:cleanErr(e)};}}

let refreshRunning=false;
async function runStateRefresh(){
  if(refreshRunning||!GITHUB_PAT)return;refreshRunning=true;
  try{
    const u="https://api.github.com/repos/namelessdhamma/nameless-dhamma-vault/contents/.github/nd-state-refresh-v2/nd-state-refresh-v2.js?ref=main";
    const r=await fetch(u,{headers:{authorization:"Bearer "+GITHUB_PAT,accept:"application/vnd.github+json","user-agent":"nd-youtube-mcp-host/1.0"}});
    if(!r.ok)throw new Error("state_refresh_source_http_"+r.status);
    const o=await r.json(),src=Buffer.from(String(o.content||"").replace(/\n/g,""),"base64").toString("utf8");
    const p="/tmp/nd-state-refresh-v2-worker.js";await writeFile(p,src);
    const child=spawn("node",[p],{env:process.env,stdio:"inherit"});child.on("exit",code=>console.log("ND_STATE_REFRESH_BACKGROUND",JSON.stringify({exit:code})));
  }catch(e){console.error("ND_STATE_REFRESH_BACKGROUND",JSON.stringify({error:cleanErr(e)}));}
  finally{refreshRunning=false;}
}

const server=createServer(async(req,res)=>{
  try{
    const u=new URL(req.url||"/","http://127.0.0.1:"+PORT);
    if(u.pathname==="/healthz"){const h=await health();return j(res,h.ok?200:503,h);}
    if(u.pathname==="/youtube/health"){const h=await health();return j(res,h.ok?200:503,h);}
    if(MCP_PATH&&u.pathname===MCP_PATH&&req.method==="POST")return await mcp(req,res);
    if(MCP_PATH&&u.pathname===MCP_PATH&&req.method==="GET")return j(res,200,{ok:true,service:"nd-youtube-full-mcp",transport:"streamable-http",methods:["POST"]});
    return j(res,404,{ok:false,error:"not_found"});
  }catch(e){return j(res,500,{ok:false,error:cleanErr(e)});}
});
server.listen(PORT,"0.0.0.0",()=>console.log("ND_YOUTUBE_MCP_READY",JSON.stringify({port:PORT,configured:!!(CLIENT_ID&&CLIENT_SECRET&&REFRESH_TOKEN&&PATH_TOKEN),writes:WRITES,tools:TOOLS.length})));
setTimeout(runStateRefresh,15000);
setInterval(runStateRefresh,60*60*1000);
