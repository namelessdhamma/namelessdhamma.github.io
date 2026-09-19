#!/usr/bin/env python3
import json, os, urllib.parse, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
TOKEN=os.environ.get("TELEGRAM_BOT_TOKEN","").strip()
CHAT_ID=os.environ.get("TELEGRAM_CHAT_ID","").strip()
COMMAND=os.environ.get("COMMAND_FILE","").strip()
RESULTS=ROOT/".nd-runtime/telegram/results"
RESULTS.mkdir(parents=True,exist_ok=True)

def tg(method,payload=None):
    if not TOKEN:
        raise RuntimeError("missing_bot_token")
    url="https://api.telegram.org/bot"+TOKEN+"/"+method
    data=urllib.parse.urlencode(payload or {}).encode()
    req=urllib.request.Request(url,data=data,method="POST")
    with urllib.request.urlopen(req,timeout=30) as r:
        obj=json.loads(r.read().decode())
    if not obj.get("ok"):
        raise RuntimeError(method+"_failed")
    return obj.get("result")

def safe_user(u):
    if not isinstance(u,dict): return {}
    return {
      "id":u.get("id"),
      "is_bot":u.get("is_bot"),
      "first_name":u.get("first_name"),
      "username":u.get("username"),
      "can_join_groups":u.get("can_join_groups"),
      "can_read_all_group_messages":u.get("can_read_all_group_messages"),
      "supports_inline_queries":u.get("supports_inline_queries")
    }

def safe_chat(c):
    if not isinstance(c,dict): return {}
    return {
      "id":c.get("id"),
      "type":c.get("type"),
      "title":c.get("title"),
      "username":c.get("username")
    }

rid=Path(COMMAND).stem if COMMAND else "manual"
out={"request_id":rid,"ok":False}
try:
    me=tg("getMe")
    private=None
    if CHAT_ID:
        private=tg("getChat",{"chat_id":CHAT_ID})
    channel=None
    channel_error=None
    try:
        channel=tg("getChat",{"chat_id":"@namelessdhamma"})
    except Exception as e:
        channel_error=type(e).__name__
    membership=None
    membership_error=None
    try:
        membership=tg("getChatMember",{"chat_id":"@namelessdhamma","user_id":me.get("id")})
    except Exception as e:
        membership_error=type(e).__name__
    out={
      "request_id":rid,
      "ok":True,
      "bot":safe_user(me),
      "private_chat_configured":bool(CHAT_ID),
      "private_chat":safe_chat(private) if private else None,
      "channel":safe_chat(channel) if channel else None,
      "channel_lookup_error":channel_error,
      "channel_membership_status":(membership or {}).get("status") if isinstance(membership,dict) else None,
      "channel_can_post_messages":(membership or {}).get("can_post_messages") if isinstance(membership,dict) else None,
      "channel_can_edit_messages":(membership or {}).get("can_edit_messages") if isinstance(membership,dict) else None,
      "channel_membership_error":membership_error
    }
except Exception as e:
    out={"request_id":rid,"ok":False,"error":type(e).__name__}

(RESULTS/(rid+".json")).write_text(json.dumps(out,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
if not out.get("ok"):
    raise SystemExit(1)
