import fs from 'node:fs';
import crypto from 'node:crypto';

const STATE_PATH = process.env.ND_TIKTOK_STATE_PATH || 'tmp/tiktok-github-token-state.json';
const CLIENT_KEY = process.env.ND_TIKTOK_GH_CLIENT_KEY || '';
const CLIENT_SECRET = process.env.ND_TIKTOK_GH_CLIENT_SECRET || '';
const STATE_KEY = process.env.ND_TIKTOK_GH_STATE_KEY || '';
const TOOL = process.argv[2] || 'tiktok_user';
const ARG_JSON = process.argv[3] || '{}';

function die(msg) { throw new Error(msg); }
function deriveKey() { return crypto.createHash('sha256').update(STATE_KEY, 'utf8').digest(); }

function decryptState() {
  if (!STATE_KEY) die('state_key_missing');
  const env = JSON.parse(fs.readFileSync(STATE_PATH, 'utf8'));
  if (env.version !== 1 || env.algorithm !== 'AES-256-GCM') die('unsupported_state_envelope');
  const decipher = crypto.createDecipheriv('aes-256-gcm', deriveKey(), Buffer.from(env.iv, 'base64'));
  decipher.setAuthTag(Buffer.from(env.tag, 'base64'));
  const plain = Buffer.concat([
    decipher.update(Buffer.from(env.ciphertext, 'base64')),
    decipher.final()
  ]);
  const state = JSON.parse(plain.toString('utf8'));
  if (!state.refresh_token) die('refresh_token_missing');
  return state;
}

function encryptState(state) {
  const iv = crypto.randomBytes(12);
  const cipher = crypto.createCipheriv('aes-256-gcm', deriveKey(), iv);
  const plain = Buffer.from(JSON.stringify(state), 'utf8');
  const ciphertext = Buffer.concat([cipher.update(plain), cipher.final()]);
  const tag = cipher.getAuthTag();
  const env = {
    version: 1,
    algorithm: 'AES-256-GCM',
    iv: iv.toString('base64'),
    tag: tag.toString('base64'),
    ciphertext: ciphertext.toString('base64'),
    updated_at: new Date().toISOString()
  };
  fs.writeFileSync(STATE_PATH, JSON.stringify(env, null, 2) + '\n');
}

async function jsonOrText(r) {
  const t = await r.text();
  try { return JSON.parse(t || '{}'); } catch { return {raw: t.slice(0, 2000)}; }
}

async function refreshToken(state) {
  if (!CLIENT_KEY || !CLIENT_SECRET) die('client_credentials_missing');
  const body = new URLSearchParams({
    client_key: CLIENT_KEY,
    client_secret: CLIENT_SECRET,
    grant_type: 'refresh_token',
    refresh_token: state.refresh_token
  });
  const r = await fetch('https://open.tiktokapis.com/v2/oauth/token/', {
    method: 'POST',
    headers: {'Content-Type': 'application/x-www-form-urlencoded', 'Cache-Control': 'no-cache'},
    body
  });
  const obj = await jsonOrText(r);
  if (!r.ok || obj.error) die('token_refresh_failed:' + r.status + ':' + JSON.stringify(obj));
  const now = Math.floor(Date.now()/1000);
  const next = {
    ...state,
    ...obj,
    refresh_token: obj.refresh_token || state.refresh_token,
    open_id: obj.open_id || state.open_id || '',
    scope: obj.scope || state.scope || '',
    credential_mode: state.credential_mode || 'sandbox',
    obtained_at: now,
    expires_at: now + Number(obj.expires_in || 0)
  };
  if (obj.refresh_expires_in) next.refresh_expires_at = now + Number(obj.refresh_expires_in);
  encryptState(next);
  return next;
}

async function api(state, url, method='GET', body=null, extraHeaders={}) {
  const headers = {Authorization: 'Bearer ' + state.access_token, Accept: 'application/json', ...extraHeaders};
  let payload = body;
  if (body && typeof body === 'object' && !(body instanceof Uint8Array) && !Buffer.isBuffer(body)) {
    headers['Content-Type'] = 'application/json; charset=UTF-8';
    payload = JSON.stringify(body);
  }
  const r = await fetch(url, {method, headers, body: payload});
  const obj = await jsonOrText(r);
  if (!r.ok) die('tiktok_http_' + r.status + ':' + JSON.stringify(obj));
  if (obj?.error?.code && obj.error.code !== 'ok') die('tiktok_api_error:' + JSON.stringify(obj.error));
  return obj;
}

async function uploadBinary(url, buf, mime='video/mp4') {
  const r = await fetch(url, {
    method: 'PUT',
    headers: {
      'Content-Type': mime,
      'Content-Length': String(buf.length),
      'Content-Range': `bytes 0-${buf.length-1}/${buf.length}`
    },
    body: buf
  });
  if (!r.ok) die('upload_http_' + r.status + ':' + (await r.text()).slice(0,1000));
  return r.status;
}

function args() {
  const a = JSON.parse(ARG_JSON);
  if (!a || typeof a !== 'object' || Array.isArray(a)) die('arguments_must_be_object');
  return a;
}

async function toolCall(state, name, a) {
  if (name === 'tiktok_status') {
    return {ok:true, route:'github-actions-direct', authorized:!!state.access_token, scope:state.scope||'', open_id_present:!!state.open_id, credential_mode:state.credential_mode||'sandbox'};
  }
  if (name === 'tiktok_user') {
    const fields='open_id,union_id,avatar_url,avatar_large_url,display_name,username,bio_description,profile_deep_link,is_verified,follower_count,following_count,likes_count,video_count';
    return api(state, 'https://open.tiktokapis.com/v2/user/info/?fields=' + encodeURIComponent(fields).replace(/%2C/g, ','));
  }
  if (name === 'tiktok_list_videos') {
    const fields='id,title,video_description,duration,cover_image_url,embed_link,create_time';
    const body={max_count:Math.max(1,Math.min(20,Number(a.max_count||10)))};
    if (a.cursor !== undefined) body.cursor=Number(a.cursor);
    return api(state, 'https://open.tiktokapis.com/v2/video/list/?fields=' + encodeURIComponent(fields).replace(/%2C/g, ','), 'POST', body);
  }
  if (name === 'tiktok_creator_info') {
    return api(state, 'https://open.tiktokapis.com/v2/post/publish/creator_info/query/', 'POST', {});
  }
  if (name === 'tiktok_publish_status') {
    if (!a.publish_id) die('publish_id_required');
    return api(state, 'https://open.tiktokapis.com/v2/post/publish/status/fetch/', 'POST', {publish_id:String(a.publish_id)});
  }
  if (name === 'tiktok_upload_draft_base64') {
    if (!a.media_base64) die('media_base64_required');
    const mime=String(a.mime_type||'video/mp4');
    if (!['video/mp4','video/quicktime','video/webm'].includes(mime)) die('unsupported_video_type');
    const buf=Buffer.from(String(a.media_base64),'base64');
    if (!buf.length || buf.length > 8*1024*1024) die('media_size_invalid');
    const init=await api(state,'https://open.tiktokapis.com/v2/post/publish/inbox/video/init/','POST',{
      source_info:{source:'FILE_UPLOAD',video_size:buf.length,chunk_size:buf.length,total_chunk_count:1}
    });
    const data=init.data||{};
    if (!data.upload_url || !data.publish_id) die('upload_init_missing_fields');
    const upload_status=await uploadBinary(data.upload_url,buf,mime);
    return {ok:true,publish_id:data.publish_id,upload_status};
  }
  if (name === 'tiktok_upload_draft_url' || name === 'tiktok_direct_post_video_url') {
    const u=String(a.video_url||'');
    const allowed=['https://namelessdhamma.org/','https://www.namelessdhamma.org/','https://raw.githubusercontent.com/namelessdhamma/'];
    if (!allowed.some(p=>u.startsWith(p))) die('media_url_not_approved');
    const mr=await fetch(u);
    if (!mr.ok) die('media_download_http_'+mr.status);
    const buf=Buffer.from(await mr.arrayBuffer());
    if (!buf.length || buf.length>70*1024*1024) die('media_size_invalid');
    const mime=(mr.headers.get('content-type')||'video/mp4').split(';')[0];
    if (name === 'tiktok_upload_draft_url') {
      return toolCall(state,'tiktok_upload_draft_base64',{media_base64:buf.toString('base64'),mime_type:mime==='application/octet-stream'?'video/mp4':mime});
    }
    const post_info={
      privacy_level:String(a.privacy_level||'SELF_ONLY'),
      title:String(a.title||'').slice(0,2200),
      disable_duet:!!a.disable_duet,
      disable_comment:!!a.disable_comment,
      disable_stitch:!!a.disable_stitch
    };
    const init=await api(state,'https://open.tiktokapis.com/v2/post/publish/video/init/','POST',{
      post_info,
      source_info:{source:'FILE_UPLOAD',video_size:buf.length,chunk_size:buf.length,total_chunk_count:1}
    });
    const data=init.data||{};
    if (!data.upload_url || !data.publish_id) die('direct_init_missing_fields');
    const upload_status=await uploadBinary(data.upload_url,buf,mime==='application/octet-stream'?'video/mp4':mime);
    return {ok:true,publish_id:data.publish_id,upload_status};
  }
  if (name === 'tiktok_publish_photos') {
    const images=Array.isArray(a.photo_images)?a.photo_images:[];
    if (!images.length || images.length>35) die('photo_images_required');
    for (const u of images) if (!String(u).startsWith('https://namelessdhamma.org/')) die('photo_url_must_use_verified_nd_prefix');
    const mode=String(a.post_mode||'MEDIA_UPLOAD').toUpperCase();
    const post_info={title:String(a.title||'').slice(0,90),description:String(a.description||'').slice(0,4000)};
    if (mode==='DIRECT_POST') Object.assign(post_info,{
      privacy_level:String(a.privacy_level||'SELF_ONLY'),
      disable_comment:!!a.disable_comment,
      auto_add_music:!!a.auto_add_music,
      brand_content_toggle:!!a.brand_content_toggle,
      brand_organic_toggle:!!a.brand_organic_toggle
    });
    return api(state,'https://open.tiktokapis.com/v2/post/publish/content/init/','POST',{
      media_type:'PHOTO',
      post_mode:mode,
      post_info,
      source_info:{source:'PULL_FROM_URL',photo_images:images,photo_cover_index:Number(a.photo_cover_index||0)},
      is_aigc:!!a.is_aigc
    });
  }
  die('unknown_tool:' + name);
}

const raw = decryptState();
const state = await refreshToken(raw);
const result = await toolCall(state, TOOL, args());
process.stdout.write(JSON.stringify({ok:true,route:'github-actions-direct',tool:TOOL,result}, null, 2) + '\n');
