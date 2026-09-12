#!/usr/bin/env python3
import os, sys, re, json, html, imaplib, email, urllib.request, urllib.parse
from datetime import datetime, timedelta, timezone
from email.header import decode_header
from email.utils import parsedate_to_datetime

GMAIL_USER = os.getenv("GMAIL_USER", "namelessdhamma@gmail.com")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "")
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ENABLED = os.getenv("ND_MAIL_MONITOR_ENABLED", "false").lower() == "true"
WINDOW_HOURS = int(os.getenv("ND_MAIL_WINDOW_HOURS", "26"))

PASSPORT_TERMS = [
    "загранпаспорт","паспорт","очеред","консуль","иммиграц","appointment",
    "passport","consulate","immigration","queue","запис","биометр","kd-mid",
    "подтверд","confirmation","приглаш","вызов"
]
VISA_DOC_TERMS = ["виза","visa","document","документ","residence","permit","extension","продлен"]
SECURITY_TERMS = [
    "security alert","оповещение системы безопасности","password reset","password was reset",
    "personal access token","access token","new sign-in","новый вход","verification code",
    "код подтверждения","suspicious","unauthorized","2fa","two-factor"
]
BOOKING_TERMS = ["agoda","booking confirmation","reservation","бронир","hotel","flight","airasia","ticket"]
STUDY_TERMS = ["university","admission","application status","study","учеб","университет","поступлен"]
FINANCE_TERMS = ["invoice","payment","bank","card","refund","charge","оплата","банк","карта","возврат"]
ND_TERMS = [
    "nameless dhamma","railway","vercel","github actions","workflow failed","deployment failed",
    "build failed","crashed","production deployment","n8n","notebooklm"
]
KNOWN_CRITICAL_SENDERS = ["queue-robot@kd-mid.ru"]

def log(msg):
    print(msg, flush=True)

def decode_mime(value):
    if not value:
        return ""
    out = []
    for part, enc in decode_header(value):
        if isinstance(part, bytes):
            out.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            out.append(part)
    return "".join(out)

def strip_html(s):
    s = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", html.unescape(s)).strip()

def extract_text(msg, limit=5000):
    parts = []
    if msg.is_multipart():
        for p in msg.walk():
            ctype = p.get_content_type()
            disp = str(p.get("Content-Disposition") or "")
            if "attachment" in disp.lower():
                continue
            if ctype not in ("text/plain","text/html"):
                continue
            try:
                payload = p.get_payload(decode=True)
                if payload is None:
                    continue
                cs = p.get_content_charset() or "utf-8"
                txt = payload.decode(cs, errors="replace")
                parts.append(strip_html(txt) if ctype == "text/html" else txt)
            except Exception:
                continue
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                txt = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
                parts.append(strip_html(txt) if msg.get_content_type() == "text/html" else txt)
        except Exception:
            pass
    return re.sub(r"\s+", " ", " ".join(parts)).strip()[:limit]

def find_spam_mailbox(imap):
    try:
        typ, boxes = imap.list()
        if typ != "OK":
            return None
        for raw in boxes or []:
            line = raw.decode(errors="replace")
            if "\\Spam" in line:
                # mailbox is normally the quoted final token
                m = re.search(r' "([^"]+)"$', line)
                if m:
                    return m.group(1)
                m = re.search(r' ([^ ]+)$', line)
                if m:
                    return m.group(1).strip('"')
    except Exception:
        pass
    return None

def fetch_recent(imap, mailbox, cutoff):
    rows = []
    typ, _ = imap.select(f'"{mailbox}"', readonly=True)
    if typ != "OK":
        return rows
    since = (cutoff - timedelta(days=1)).strftime("%d-%b-%Y")
    typ, data = imap.search(None, "SINCE", since)
    if typ != "OK" or not data or not data[0]:
        return rows
    for num in data[0].split():
        typ, fetched = imap.fetch(num, "(RFC822 INTERNALDATE)")
        if typ != "OK" or not fetched:
            continue
        raw_msg = None
        internal = None
        for item in fetched:
            if not isinstance(item, tuple):
                continue
            meta, body = item
            raw_msg = body
            meta_s = meta.decode(errors="replace")
            m = re.search(r'INTERNALDATE "([^"]+)"', meta_s)
            if m:
                try:
                    internal = datetime.strptime(m.group(1), "%d-%b-%Y %H:%M:%S %z")
                except Exception:
                    internal = None
        if not raw_msg:
            continue
        msg = email.message_from_bytes(raw_msg)
        dt = internal
        if dt is None:
            try:
                dt = parsedate_to_datetime(msg.get("Date"))
            except Exception:
                dt = None
        if dt is not None and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt is not None and dt < cutoff:
            continue
        rows.append({
            "mailbox": mailbox,
            "date": dt.isoformat() if dt else "",
            "from": decode_mime(msg.get("From")),
            "subject": decode_mime(msg.get("Subject")),
            "text": extract_text(msg),
            "message_id": msg.get("Message-ID",""),
        })
    return rows

def classify(m):
    blob = f"{m['from']} {m['subject']} {m['text']}".lower()
    sender = m["from"].lower()
    def hit(terms): return any(t in blob for t in terms)
    if any(s in sender for s in KNOWN_CRITICAL_SENDERS) or hit(PASSPORT_TERMS):
        return (100, "passport")
    if hit(VISA_DOC_TERMS):
        return (80, "documents")
    if hit(SECURITY_TERMS):
        return (70, "security")
    if hit(BOOKING_TERMS):
        return (60, "booking")
    if hit(STUDY_TERMS):
        return (55, "study")
    if hit(FINANCE_TERMS):
        return (50, "finance")
    if hit(ND_TERMS):
        return (45, "nd")
    return (0, "other")

def compact_subject(s):
    s = re.sub(r"\s+", " ", s).strip()
    return s[:180]

def build_report(messages):
    ranked = []
    seen = set()
    for m in messages:
        score, cat = classify(m)
        if score <= 0:
            continue
        key = (m["from"].lower(), m["subject"].lower())
        if key in seen:
            continue
        seen.add(key)
        ranked.append((score, cat, m))
    ranked.sort(key=lambda x: (-x[0], x[2]["date"]))
    if not ranked:
        return "Сегодня важных писем не было"

    top = ranked[:3]
    passport = [x for x in top if x[1] == "passport"]
    if passport:
        subjects = "; ".join(compact_subject(x[2]["subject"]) for x in passport[:2])
        return f"Пришло важное письмо по загранпаспорту/консульской очереди: {subjects}. Требуется открыть письмо и выполнить указанное подтверждение или действие в установленный срок."

    labels = {
        "documents":"документы/виза","security":"безопасность","booking":"бронирование",
        "study":"учёба","finance":"финансы","nd":"Nameless Dhamma"
    }
    desc = "; ".join(f"{labels.get(cat,cat)} — {compact_subject(m['subject'])}" for _,cat,m in top)
    return f"Пришли важные письма: {desc}. Требуется проверить указанные сообщения и выполнить действие только там, где оно явно запрошено."

def tg_api(method, payload=None):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/{method}"
    data = urllib.parse.urlencode(payload or {}).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def resolve_chat_id():
    if TG_CHAT_ID:
        return TG_CHAT_ID

    # First try the normal pending-update queue.
    data = tg_api("getUpdates", {"limit": 100, "timeout": 0})
    updates = data.get("result", [])

    # If Telegram returns no pending updates, explicitly ask for the most
    # recent updates. This is useful for a newly-created private bot where
    # /start may have been sent before the first automation run.
    if not updates:
        data = tg_api("getUpdates", {"offset": -100, "limit": 100, "timeout": 0})
        updates = data.get("result", [])

    candidates = []
    for u in updates:
        msg = u.get("message") or u.get("edited_message") or u.get("channel_post") or {}
        chat = msg.get("chat") or {}
        cid = chat.get("id")
        ctype = chat.get("type")
        text = (msg.get("text") or "").strip()
        if cid and ctype == "private":
            candidates.append((1 if text.startswith("/start") else 0, u.get("update_id",0), str(cid)))

    if not candidates:
        raise RuntimeError("Telegram chat ID not found. Send any new message (for example /start) to the bot and rerun.")
    candidates.sort(reverse=True)
    return candidates[0][2]

def send_telegram(text):
    cid = resolve_chat_id()
    tg_api("sendMessage", {"chat_id": cid, "text": text, "disable_web_page_preview": "true"})
    log("telegram_send=ok")

def main():
    if not ENABLED:
        log("status=disabled")
        return 0
    if not GMAIL_APP_PASSWORD:
        raise RuntimeError("GMAIL_APP_PASSWORD is not configured")
    if not TG_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=WINDOW_HOURS)
    imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    imap.login(GMAIL_USER, GMAIL_APP_PASSWORD)
    messages = fetch_recent(imap, "INBOX", cutoff)
    spam = find_spam_mailbox(imap)
    if spam:
        messages.extend(fetch_recent(imap, spam, cutoff))
    try:
        imap.logout()
    except Exception:
        pass
    report = build_report(messages)
    send_telegram(report)
    log(f"status=ok scanned={len(messages)} important_reported={'no' if report == 'Сегодня важных писем не было' else 'yes'}")
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log("status=error")
        log(f"error={type(e).__name__}: {e}")
        sys.exit(1)
