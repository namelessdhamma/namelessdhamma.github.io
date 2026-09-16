import json, os, urllib.parse, urllib.request
from urllib.error import HTTPError

SOCIAL_PROVIDERS=("youtube","telegram","instagram","facebook","tiktok","vk","line","dzen")
WRITES_ENABLED=os.environ.get("ND_SOCIAL_WRITES_ENABLED","false").strip().lower() in ("1","true","yes","on")

SECRET_NAMES=(
    "ND_YOUTUBE_CLIENT_ID","ND_YOUTUBE_CLIENT_SECRET","ND_YOUTUBE_REFRESH_TOKEN",
    "ND_TELEGRAM_BOT_TOKEN",
    "ND_META_USER_ACCESS_TOKEN",
    "ND_TIKTOK_CLIENT_KEY","ND_TIKTOK_CLIENT_SECRET","ND_TIKTOK_REFRESH_TOKEN","ND_TIKTOK_ACCESS_TOKEN",
    "VK_GROUP_TOKEN",
    "ND_LINE_CHANNEL_ACCESS_TOKEN","ND_LINE_CHANNEL_SECRET",
    "ND_DZEN_SESSION_BUNDLE",
)

def _secret(name):
    return os.environ.get(name,"").strip()

def _redact(text):
    s=str(text)
    for name in SECRET_NAMES:
        v=_secret(name)
        if v:
            s=s.replace(v,"[REDACTED]")
            s=s.replace(urllib.parse.quote(v,safe=""),"[REDACTED]")
    return s[:1800]

def _json_request(url,method="GET",payload=None,headers=None,form=None,timeout=60):
    h=dict(headers or {})
    data=None
    if form is not None:
        data=urllib.parse.urlencode(form).encode("utf-8")
        h.setdefault("Content-Type","application/x-www-form-urlencoded")
    elif payload is not None:
        data=json.dumps(payload,ensure_ascii=False).encode("utf-8")
        h.setdefault("Content-Type","application/json")
    req=urllib.request.Request(url,data=data,headers=h,method=method)
    try:
        with urllib.request.urlopen(req,timeout=timeout) as r:
            raw=r.read().decode("utf-8","replace")
            try: obj=json.loads(raw) if raw else {}
            except Exception: obj={"raw":raw[:6000]}
            return r.status,obj
    except HTTPError as e:
        raw=e.read().decode("utf-8","replace")
        raise RuntimeError("HTTP_%s:%s"%(e.code,_redact(raw or e.reason))) from e

def _require(names):
    missing=[n for n in names if not _secret(n)]
    if missing:
        raise RuntimeError("AWAITING_AUTH:"+",".join(missing))

def _youtube_access_token():
    _require(("ND_YOUTUBE_CLIENT_ID","ND_YOUTUBE_CLIENT_SECRET","ND_YOUTUBE_REFRESH_TOKEN"))
    status,obj=_json_request(
        "https://oauth2.googleapis.com/token",method="POST",
        form={
            "client_id":_secret("ND_YOUTUBE_CLIENT_ID"),
            "client_secret":_secret("ND_YOUTUBE_CLIENT_SECRET"),
            "refresh_token":_secret("ND_YOUTUBE_REFRESH_TOKEN"),
            "grant_type":"refresh_token",
        })
    tok=str(obj.get("access_token") or "")
    if status!=200 or not tok:
        raise RuntimeError("youtube_refresh_failed")
    return tok

def youtube(cmd):
    op=str(cmd.get("operation") or "status").strip().lower()
    if op not in ("status","account"):
        if not WRITES_ENABLED:
            raise RuntimeError("WRITE_NOT_QUALIFIED")
        raise RuntimeError("youtube_operation_not_implemented")
    token=_youtube_access_token()
    url="https://www.googleapis.com/youtube/v3/channels?"+urllib.parse.urlencode({
        "part":"id,snippet,statistics",
        "mine":"true",
        "maxResults":"10",
    })
    _,obj=_json_request(url,headers={"Authorization":"Bearer "+token})
    items=obj.get("items") or []
    safe=[]
    for x in items:
        sn=x.get("snippet") or {}; st=x.get("statistics") or {}
        safe.append({
            "id":x.get("id"),
            "title":sn.get("title"),
            "customUrl":sn.get("customUrl"),
            "subscriberCount":st.get("subscriberCount"),
            "videoCount":st.get("videoCount"),
            "viewCount":st.get("viewCount"),
        })
    return {"transport":"github_actions_to_youtube_api","operation":op,"accounts":safe}

def telegram(cmd):
    op=str(cmd.get("operation") or "status").strip().lower()
    if op not in ("status","account"):
        if not WRITES_ENABLED:
            raise RuntimeError("WRITE_NOT_QUALIFIED")
        raise RuntimeError("telegram_operation_not_implemented")
    _require(("ND_TELEGRAM_BOT_TOKEN",))
    token=_secret("ND_TELEGRAM_BOT_TOKEN")
    _,me=_json_request("https://api.telegram.org/bot"+token+"/getMe")
    out={"bot":me.get("result")}
    chat=os.environ.get("ND_TELEGRAM_CHANNEL_ID","").strip()
    if chat:
        try:
            _,info=_json_request("https://api.telegram.org/bot"+token+"/getChat?"+urllib.parse.urlencode({"chat_id":chat}))
            out["channel"]=info.get("result")
        except Exception as e:
            out["channel_probe_error"]=_redact(e)
    return {"transport":"github_actions_to_telegram_bot_api","operation":op,**out}

def _meta_get(path,params):
    _require(("ND_META_USER_ACCESS_TOKEN",))
    version=os.environ.get("ND_META_GRAPH_VERSION","v24.0").strip() or "v24.0"
    p=dict(params); p["access_token"]=_secret("ND_META_USER_ACCESS_TOKEN")
    url="https://graph.facebook.com/"+version+"/"+path.lstrip("/")+"?"+urllib.parse.urlencode(p)
    return _json_request(url)

def facebook(cmd):
    op=str(cmd.get("operation") or "status").strip().lower()
    if op not in ("status","account"):
        if not WRITES_ENABLED: raise RuntimeError("WRITE_NOT_QUALIFIED")
        raise RuntimeError("facebook_operation_not_implemented")
    page=os.environ.get("ND_FACEBOOK_PAGE_ID","").strip()
    if page:
        _,obj=_meta_get(page,{"fields":"id,name,username,followers_count"})
        return {"transport":"github_actions_to_meta_graph_api","operation":op,"page":obj}
    _,obj=_meta_get("me/accounts",{"fields":"id,name,username"})
    return {"transport":"github_actions_to_meta_graph_api","operation":op,"pages":obj.get("data") or []}

def instagram(cmd):
    op=str(cmd.get("operation") or "status").strip().lower()
    if op not in ("status","account"):
        if not WRITES_ENABLED: raise RuntimeError("WRITE_NOT_QUALIFIED")
        raise RuntimeError("instagram_operation_not_implemented")
    ig=os.environ.get("ND_INSTAGRAM_USER_ID","").strip()
    if not ig:
        raise RuntimeError("AWAITING_AUTH:ND_INSTAGRAM_USER_ID")
    _,obj=_meta_get(ig,{"fields":"id,username,account_type,media_count"})
    return {"transport":"github_actions_to_instagram_graph_api","operation":op,"account":obj}

def _tiktok_access_token():
    direct=_secret("ND_TIKTOK_ACCESS_TOKEN")
    if direct: return direct
    _require(("ND_TIKTOK_CLIENT_KEY","ND_TIKTOK_CLIENT_SECRET","ND_TIKTOK_REFRESH_TOKEN"))
    _,obj=_json_request(
        "https://open.tiktokapis.com/v2/oauth/token/",method="POST",
        form={
            "client_key":_secret("ND_TIKTOK_CLIENT_KEY"),
            "client_secret":_secret("ND_TIKTOK_CLIENT_SECRET"),
            "grant_type":"refresh_token",
            "refresh_token":_secret("ND_TIKTOK_REFRESH_TOKEN"),
        })
    tok=str(obj.get("access_token") or "")
    if not tok: raise RuntimeError("tiktok_refresh_failed")
    return tok

def tiktok(cmd):
    op=str(cmd.get("operation") or "status").strip().lower()
    if op not in ("status","account"):
        if not WRITES_ENABLED: raise RuntimeError("WRITE_NOT_QUALIFIED")
        raise RuntimeError("tiktok_operation_not_implemented")
    token=_tiktok_access_token()
    url="https://open.tiktokapis.com/v2/user/info/?"+urllib.parse.urlencode({
        "fields":"open_id,union_id,avatar_url,display_name"
    })
    _,obj=_json_request(url,headers={"Authorization":"Bearer "+token})
    return {"transport":"github_actions_to_tiktok_api","operation":op,"account":((obj.get("data") or {}).get("user") or {})}

def vk(cmd):
    op=str(cmd.get("operation") or "status").strip().lower()
    if op not in ("status","account"):
        if not WRITES_ENABLED: raise RuntimeError("WRITE_NOT_QUALIFIED")
        raise RuntimeError("vk_operation_not_implemented")
    _require(("VK_GROUP_TOKEN",))
    group=os.environ.get("VK_GROUP_ID","").strip() or os.environ.get("VK_GROUP_SCREEN_NAME","").strip() or "namelessdhamma"
    version=os.environ.get("VK_API_VERSION","5.199").strip() or "5.199"
    url="https://api.vk.com/method/groups.getById?"+urllib.parse.urlencode({
        "group_id":group,"fields":"members_count,screen_name,name","access_token":_secret("VK_GROUP_TOKEN"),"v":version
    })
    _,obj=_json_request(url)
    if obj.get("error"): raise RuntimeError("vk_api_error:"+_redact(obj.get("error")))
    return {"transport":"github_actions_to_vk_api","operation":op,"group":obj.get("response")}

def line(cmd):
    op=str(cmd.get("operation") or "status").strip().lower()
    if op not in ("status","account"):
        if not WRITES_ENABLED: raise RuntimeError("WRITE_NOT_QUALIFIED")
        raise RuntimeError("line_operation_not_implemented")
    _require(("ND_LINE_CHANNEL_ACCESS_TOKEN",))
    _,obj=_json_request("https://api.line.me/v2/bot/info",headers={"Authorization":"Bearer "+_secret("ND_LINE_CHANNEL_ACCESS_TOKEN")})
    return {"transport":"github_actions_to_line_messaging_api","operation":op,"account":obj}

def dzen(cmd):
    op=str(cmd.get("operation") or "status").strip().lower()
    if op not in ("status","account"):
        if not WRITES_ENABLED: raise RuntimeError("WRITE_NOT_QUALIFIED")
        raise RuntimeError("dzen_operation_not_qualified")
    if not _secret("ND_DZEN_SESSION_BUNDLE"):
        raise RuntimeError("AWAITING_AUTH:ND_DZEN_SESSION_BUNDLE")
    return {
        "transport":"github_actions_to_dzen_experimental_session",
        "operation":op,
        "status":"SESSION_PRESENT_UNQUALIFIED",
        "experimental":True,
        "official_api":False,
    }

ROUTERS={
    "youtube":youtube,
    "telegram":telegram,
    "instagram":instagram,
    "facebook":facebook,
    "tiktok":tiktok,
    "vk":vk,
    "line":line,
    "dzen":dzen,
}

def route_social(provider,cmd):
    p=str(provider or "").strip().lower()
    if p not in ROUTERS:
        raise RuntimeError("unsupported_social_provider")
    return ROUTERS[p](cmd)
