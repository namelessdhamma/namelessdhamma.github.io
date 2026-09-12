#!/usr/bin/env python3
import os, sys, re, json, html, imaplib, email, urllib.request, urllib.parse
from datetime import datetime, timezone
from email.header import decode_header
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

GMAIL_USER = os.getenv("GMAIL_USER", "namelessdhamma@gmail.com")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "").replace(" ", "")
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
ENABLED = os.getenv("ND_MAIL_MONITOR_ENABLED", "false").lower() == "true"
LOCAL_TZ = ZoneInfo(os.getenv("ND_MAIL_TIMEZONE", "Asia/Bangkok"))

KNOWN_PASSPORT_SENDERS = ("queue-robot@kd-mid.ru",)
PASSPORT_SUBJECT_TERMS = (
    "загранпаспорт", "биометрический паспорт", "паспортная заяв", "место в очеред",
    "очередь на паспорт", "консульств", "иммиграц", "passport", "consulate",
    "immigration", "appointment for passport", "passport queue",
)
VISA_SUBJECT_TERMS = (
    "visa", "виза", "residence permit", "вид на жительство",
    "extension of stay", "продление пребывания", "immigration appointment",
)
SECURITY_SUBJECT_TERMS = (
    "security alert", "оповещение системы безопасности", "password reset",
    "password was reset", "пароль измен", "new sign-in", "новый вход",
    "verification code", "код подтверждения", "unauthorized", "suspicious",
    "two-factor", "двухэтапная", "oauth application has been added",
    "personal access token", "fine-grained token",
)
BOOKING_SUBJECT_TERMS = (
    "booking confirmation", "reservation confirmed", "booking confirmed",
    "подтверждение бронирования", "бронирование подтверждено", "agoda booking",
    "flight confirmation", "ticket confirmation",
)
STUDY_SUBJECT_TERMS = (
    "admission decision", "application status", "offer of admission",
    "enrollment", "зачислен", "поступлен", "статус заявления",
)
FINANCE_SUBJECT_TERMS = (
    "payment failed", "card declined", "chargeback", "refund issued",
    "invoice overdue", "оплата не прошла", "платёж отклон", "возврат средств",
)
PERSONAL_SUBJECT_TERMS = (
    "личное сообщение", "личных сообщения", "private message", "direct message",
)
ND_FAILURE_SUBJECT_TERMS = (
    "build failed", "deployment failed", "run failed", "workflow failed",
    "crashed", "production deployment failed", "service unavailable",
    "incident", "error in scenario",
)
NOISE_SENDERS = (
    "comments-noreply@docs.google.com",
    "info@make.com",
    "marketing.",
    "newsletter.",
)
NOISE_SUBJECT_TERMS = (
    "welcome to ", "start here", "getting started", "newsletter",
    "you’re close to getting your first workflow running",
    "you're close to getting your first workflow running",
)

def log(msg):
    print(msg, flush=True)

def norm(s):
    return re.sub(r"\s+", " ", (s or "")).strip()

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
    return norm(html.unescape(s))

def extract_text(msg, limit=3500):
    parts = []
    if msg.is_multipart():
        for p in msg.walk():
            ctype = p.get_content_type()
            disp = str(p.get("Content-Disposition") or "")
            if "attachment" in disp.lower() or ctype not in ("text/plain", "text/html"):
                continue
            try:
                payload = p.get_payload(decode=True)
                if payload is None:
                    continue
                txt = payload.decode(p.get_content_charset() or "utf-8", errors="replace")
                parts.append(strip_html(txt) if ctype == "text/html" else txt)
            except Exception:
                pass
    else:
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                txt = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
                parts.append(strip_html(txt) if msg.get_content_type() == "text/html" else txt)
        except Exception:
            pass
    return norm(" ".join(parts))[:limit]

def today_bounds_utc():
    now_local = datetime.now(LOCAL_TZ)
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_local.astimezone(timezone.utc), now_local.astimezone(timezone.utc), now_local.date().isoformat()

def find_spam_mailbox(imap):
    try:
        typ, boxes = imap.list()
        if typ != "OK":
            return None
        for raw in boxes or []:
            line = raw.decode(errors="replace")
            if "\\Spam" in line:
                m = re.search(r' "([^"]+)"$', line)
                if m:
                    return m.group(1)
                m = re.search(r' ([^ ]+)$', line)
                if m:
                    return m.group(1).strip('"')
    except Exception:
        pass
    return None

def fetch_today(imap, mailbox, start_utc, end_utc):
    rows = []
    typ, _ = imap.select(f'"{mailbox}"', readonly=True)
    if typ != "OK":
        return rows

    # IMAP SINCE is date-granular; exact Bangkok-day filtering is done below.
    since = start_utc.strftime("%d-%b-%Y")
    typ, data = imap.search(None, "SINCE", since)
    if typ != "OK" or not data or not data[0]:
        return rows

    for num in data[0].split():
        typ, fetched = imap.fetch(num, "(RFC822 INTERNALDATE)")
        if typ != "OK" or not fetched:
            continue

        raw_msg, internal = None, None
        for item in fetched:
            if not isinstance(item, tuple):
                continue
            meta, body = item
            raw_msg = body
            m = re.search(r'INTERNALDATE "([^"]+)"', meta.decode(errors="replace"))
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
        if dt is None:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_utc = dt.astimezone(timezone.utc)
        if not (start_utc <= dt_utc <= end_utc):
            continue

        rows.append({
            "mailbox": mailbox,
            "date": dt_utc.isoformat(),
            "local_time": dt_utc.astimezone(LOCAL_TZ).strftime("%H:%M"),
            "from": decode_mime(msg.get("From")),
            "subject": decode_mime(msg.get("Subject")),
            "text": extract_text(msg),
            "message_id": msg.get("Message-ID", ""),
        })
    return rows

def contains(text, terms):
    t = (text or "").lower()
    return any(term in t for term in terms)

def category_for(m):
    sender = m["from"].lower()
    subject = norm(m["subject"]).lower()

    if any(s in sender for s in KNOWN_PASSPORT_SENDERS):
        return 100, "passport"

    if any(s in sender for s in NOISE_SENDERS):
        return 0, "other"
    if contains(subject, NOISE_SUBJECT_TERMS):
        return 0, "other"

    # High precision: semantic categories come primarily from sender + subject,
    # not arbitrary words buried in mail bodies or automated logs.
    if contains(subject, PASSPORT_SUBJECT_TERMS):
        return 95, "passport"
    if contains(subject, VISA_SUBJECT_TERMS):
        return 85, "visa"
    if contains(subject, SECURITY_SUBJECT_TERMS):
        return 80, "security"
    if contains(subject, BOOKING_SUBJECT_TERMS):
        return 75, "booking"
    if contains(subject, STUDY_SUBJECT_TERMS):
        return 70, "study"
    if contains(subject, FINANCE_SUBJECT_TERMS):
        return 70, "finance"
    if contains(subject, PERSONAL_SUBJECT_TERMS):
        return 55, "personal"
    if contains(subject, ND_FAILURE_SUBJECT_TERMS):
        return 65, "nd_failure"

    # Sender-aware fallbacks for known operational systems.
    if "notifications@vercel.com" in sender and ("failed" in subject or "error" in subject):
        return 65, "nd_failure"
    if "notify.railway.app" in sender and ("failed" in subject or "crashed" in subject):
        return 65, "nd_failure"
    if "notifications@github.com" in sender and ("run failed" in subject or "workflow failed" in subject):
        return 65, "nd_failure"

    return 0, "other"

def compact_subject(s):
    s = norm(s)
    return s[:145]

def group_key(cat, m):
    subject = compact_subject(m["subject"]).lower()
    if cat == "nd_failure":
        # Collapse repeated CI/deployment alerts that differ only by commit/run hashes.
        normalized = re.sub(r"\([0-9a-f]{6,40}\)", "(commit)", subject)
        normalized = re.sub(r"\b[0-9a-f]{7,40}\b", "commit", normalized)
        return cat, normalized
    return cat, m["from"].lower(), subject

def report_item(cat, items):
    m = items[-1]
    subject = html.escape(compact_subject(m["subject"]))
    count = len(items)
    suffix = f" · повторов: {count}" if count > 1 else ""

    labels = {
        "passport": "Загранпаспорт / консульство",
        "visa": "Виза / иммиграция",
        "security": "Безопасность",
        "booking": "Бронирование",
        "study": "Учёба",
        "finance": "Финансы",
        "personal": "Личные сообщения",
        "nd_failure": "ND — технический сбой",
    }
    label = labels.get(cat, "Важное письмо")
    return f"<b>{label}</b>\n• {subject}{suffix}"

def build_report(messages):
    grouped = {}
    for m in messages:
        score, cat = category_for(m)
        if score <= 0:
            continue
        key = group_key(cat, m)
        if key not in grouped:
            grouped[key] = {"score": score, "cat": cat, "items": []}
        grouped[key]["items"].append(m)

    if not grouped:
        return "Сегодня важных писем не было"

    groups = sorted(
        grouped.values(),
        key=lambda g: (-g["score"], g["items"][-1]["date"])
    )

    # Passport acquisition is the primary purpose of this monitor.
    passport_groups = [g for g in groups if g["cat"] == "passport"]
    if passport_groups:
        items = [report_item(g["cat"], g["items"]) for g in passport_groups[:3]]
        return (
            "🚨 <b>ЗАГРАНПАСПОРТ — ПРИОРИТЕТ №1</b>\n\n"
            + "\n\n".join(items)
            + "\n\n<b>Действие</b>\n"
              "Откройте письмо и выполните указанное действие по получению нового загранпаспорта в установленный срок."
        )

    # Otherwise keep the Telegram report short, scannable and useful.
    top = groups[:4]
    items = [report_item(g["cat"], g["items"]) for g in top]

    has_action_critical = any(g["cat"] in ("visa", "security", "finance") for g in top)
    action = (
        "Откройте эти письма и выполните действие только там, где оно действительно запрошено."
        if has_action_critical
        else "Немедленного действия не требуется."
    )
    return (
        "📬 <b>Сегодня важное</b>\n\n"
        + "\n\n".join(items)
        + "\n\n<b>Действие</b>\n"
        + action
    )

def tg_api(method, payload=None):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/{method}"
    data = urllib.parse.urlencode(payload or {}).encode()
    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def resolve_chat_id():
    if TG_CHAT_ID:
        return TG_CHAT_ID

    data = tg_api("getUpdates", {"limit": 100, "timeout": 0})
    updates = data.get("result", [])
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
            candidates.append((1 if text.startswith("/start") else 0, u.get("update_id", 0), str(cid)))

    if not candidates:
        raise RuntimeError("Telegram chat ID not found. Send any new message to the bot and rerun.")
    candidates.sort(reverse=True)
    return candidates[0][2]

def send_telegram(text):
    cid = resolve_chat_id()
    tg_api("sendMessage", {
        "chat_id": cid,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    })
    log("telegram_send=ok")

def main():
    if not ENABLED:
        log("status=disabled")
        return 0
    if not GMAIL_APP_PASSWORD:
        raise RuntimeError("GMAIL_APP_PASSWORD is not configured")
    if not TG_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

    start_utc, end_utc, local_date = today_bounds_utc()

    imap = imaplib.IMAP4_SSL("imap.gmail.com", 993)
    imap.login(GMAIL_USER, GMAIL_APP_PASSWORD)

    messages = fetch_today(imap, "INBOX", start_utc, end_utc)
    spam = find_spam_mailbox(imap)
    if spam:
        messages.extend(fetch_today(imap, spam, start_utc, end_utc))

    try:
        imap.logout()
    except Exception:
        pass

    report = build_report(messages)
    send_telegram(report)
    log(
        f"status=ok date={local_date} scanned={len(messages)} "
        f"important_reported={'no' if report == 'Сегодня важных писем не было' else 'yes'}"
    )
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log("status=error")
        log(f"error={type(e).__name__}: {e}")
        sys.exit(1)
