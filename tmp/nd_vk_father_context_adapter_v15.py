import hashlib
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime, timezone

READ_URL = os.environ.get('ND_FATHER_CONTEXT_READ_URL', '').strip()
APPEND_URL = os.environ.get('ND_FATHER_CONTEXT_APPEND_URL', '').strip()
ND_READ_URL = os.environ.get('ND_FATHER_ND_READ_URL', '').strip()
ND_READ_TOKEN = (os.environ.get('ND_FATHER_ND_READ_TOKEN', '') or os.environ.get('QSTASH_TOKEN', '')).strip()

COLUMNS = [
    'artifact_id','version','chunk_index','chunk_count','operation','kind','status','authority',
    'created_at','updated_at','actor','sender_vk_id','provider','actual_model','gateway_version',
    'broker_version','idempotency_hash','source_refs_json','title','source_ref','content_chunk',
    'previous_version','record_hash'
]

ALLOWED_CONTEXT_KINDS = {'conversation_turn', 'qualification_context_turn'}
MAX_REMOTE_ROWS = 200
DEFAULT_TURNS = 10
DEFAULT_CONTEXT_CHARS = 24000
DEFAULT_ND_CONTEXT_CHARS = 12000


def _json_request(url, *, data=None, headers=None, method=None, timeout=15):
    if not url:
        raise RuntimeError('father_context_endpoint_not_configured')
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read(1500000).decode('utf-8', 'replace')
    return json.loads(raw)


def _rows_from_values(payload):
    values = payload.get('values') or []
    if not values:
        return []
    header = [str(x) for x in values[0]]
    if header[:len(COLUMNS)] != COLUMNS[:len(header)]:
        raise RuntimeError('father_context_schema_mismatch')
    out = []
    for row in values[1:MAX_REMOTE_ROWS]:
        padded = list(row) + [''] * max(0, len(header) - len(row))
        out.append(dict(zip(header, padded)))
    return out


def read_context_rows():
    return _rows_from_values(_json_request(READ_URL, timeout=15))


def hydrate_user(uid, *, max_turns=DEFAULT_TURNS, max_chars=DEFAULT_CONTEXT_CHARS):
    uid = str(int(uid))
    selected = []
    for row in read_context_rows():
        if str(row.get('sender_vk_id', '')) != uid:
            continue
        if row.get('operation') != 'append' or row.get('kind') not in ALLOWED_CONTEXT_KINDS:
            continue
        if row.get('status') not in ('committed', 'active', 'qualification'):
            continue
        try:
            item = json.loads(row.get('content_chunk') or '{}')
        except Exception:
            continue
        role = str(item.get('role') or '')
        content = str(item.get('content') or '')
        if role not in ('user', 'assistant') or not content:
            continue
        selected.append((str(row.get('created_at') or ''), {'role': role, 'content': content[:12000]}))
    selected.sort(key=lambda x: x[0])
    messages = [x[1] for x in selected[-max(1, int(max_turns)):]]
    while messages and sum(len(m['content']) for m in messages) > max_chars:
        messages.pop(0)
    return messages


def _record(uid, role, content, *, event_id, provider='', model='', source_refs=None, status='committed'):
    uid = str(int(uid))
    role = str(role)
    if role not in ('user', 'assistant'):
        raise ValueError('role_must_be_user_or_assistant')
    content = str(content)[:12000]
    event_id = str(event_id)
    idem = hashlib.sha256(('nd-vk-context:'+uid+':'+event_id+':'+role).encode()).hexdigest()
    now = datetime.now(timezone.utc).isoformat()
    chunk = json.dumps({'role': role, 'content': content}, ensure_ascii=False, separators=(',', ':'))
    record_hash = hashlib.sha256((idem+'|'+chunk).encode()).hexdigest()
    return {
        'artifact_id': 'vkctx-'+idem[:24], 'version': '1', 'chunk_index': '0', 'chunk_count': '1',
        'operation': 'append', 'kind': 'conversation_turn', 'status': status,
        'authority': 'ND_FATHER_WORKSPACE', 'created_at': now, 'updated_at': now,
        'actor': 'ND_VK_GATEWAY', 'sender_vk_id': uid, 'provider': str(provider)[:120],
        'actual_model': str(model)[:180], 'gateway_version': 'V15-context-candidate',
        'broker_version': 'father-workspace-make-q1', 'idempotency_hash': idem,
        'source_refs_json': json.dumps(source_refs or [], ensure_ascii=False, separators=(',', ':'))[:3000],
        'title': 'vk-conversation-turn', 'source_ref': 'ND Father — Inbox Ledger',
        'content_chunk': chunk, 'previous_version': '', 'record_hash': record_hash,
    }


def append_turn(uid, role, content, *, event_id, provider='', model='', source_refs=None, status='committed'):
    record = _record(uid, role, content, event_id=event_id, provider=provider, model=model,
                     source_refs=source_refs, status=status)
    # POST form keeps conversation text out of the URL/query string. The Make webhook is the bounded
    # credentialed bridge to the existing Father Workspace ledger; no Google credential enters Railway.
    body = urllib.parse.urlencode(record).encode('utf-8')
    response = _json_request(APPEND_URL, data=body,
                             headers={'Content-Type':'application/x-www-form-urlencoded'},
                             method='POST', timeout=15)
    if not response.get('ok'):
        raise RuntimeError('father_context_append_failed')
    return {'ok': True, 'artifact_id': record['artifact_id'], 'idempotency_hash': record['idempotency_hash'],
            'row': response.get('row')}


def _normalize_nd_context(payload, *, max_chars=DEFAULT_ND_CONTEXT_CHARS):
    """Normalize either a compact projection or the existing Safe Tool Broker /nd/context shape."""
    max_chars = max(0, int(max_chars))
    if 'text' in payload:
        text = str(payload.get('text') or '')[:max_chars]
        sources = payload.get('sources') or []
        if not isinstance(sources, list):
            sources = []
        clean_sources = []
        for s in sources[:20]:
            if isinstance(s, dict) and s.get('source_ref'):
                clean_sources.append({
                    'source_ref': str(s.get('source_ref'))[:500],
                    'title': str(s.get('title') or '')[:500],
                    'authority': str(s.get('authority') or '')[:80],
                })
        return {'text': text, 'sources': clean_sources}

    pieces = payload.get('pieces') or []
    if not isinstance(pieces, list):
        pieces = []
    selected = []
    sources = []
    used = 0
    for p in pieces[:12]:
        if not isinstance(p, dict):
            continue
        authority = str(p.get('authority') or '').upper()
        # Father gets only governed authoritative/canonical context here. Discovery/non-auth material
        # remains available through separate research paths and is not silently injected as ND truth.
        if authority not in ('AUTHORITATIVE', 'CANONICAL'):
            continue
        label = str(p.get('label') or 'ND context')[:500]
        text = str(p.get('text') or '')
        if not text or used >= max_chars:
            continue
        room = max_chars - used
        text = text[:room]
        selected.append(label + '\n' + text)
        used += len(text)
        sources.append({'source_ref': label, 'title': label, 'authority': authority})
    return {
        'text': '\n\n'.join(selected)[:max_chars],
        'sources': sources[:20],
        'statehead_status': payload.get('statehead_status'),
        'registry_version': payload.get('registry_version'),
    }


def read_nd_context(*, query='ND current architecture and relevant project context', max_chars=DEFAULT_ND_CONTEXT_CHARS):
    if not ND_READ_URL:
        return {'text': '', 'sources': []}
    url = ND_READ_URL
    # Existing V7 Safe Tool Broker exposes GET /nd/context?q=... under bearer auth.
    if '{query}' in url:
        url = url.replace('{query}', urllib.parse.quote(str(query)[:6000], safe=''))
    elif '/nd/context' in url and 'q=' not in url:
        sep = '&' if '?' in url else '?'
        url = url + sep + 'q=' + urllib.parse.quote(str(query)[:6000], safe='')
    headers = {'User-Agent': 'ND-VK-Father-Context-V15/1.0'}
    if ND_READ_TOKEN:
        headers['Authorization'] = 'Bearer ' + ND_READ_TOKEN
    payload = _json_request(url, headers=headers, timeout=20)
    return _normalize_nd_context(payload, max_chars=max_chars)
