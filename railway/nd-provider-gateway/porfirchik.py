# Порфирчик V21: собеседник сообщества Nameless Dhamma во ВКонтакте.
#
# Как он работает, по шагам:
# 1. ВК присылает событие message_new на CALLBACK_PATH. Сразу отвечаем "ok".
# 2. Ждём DEBOUNCE секунд: если человек пишет несколько сообщений подряд, отвечаем на все сразу.
# 3. Берём из ВК последние HISTORY_MESSAGES сообщений диалога, свежие почти целиком, старые сжато.
# 4. Спрашиваем самую сильную доступную модель из POOL. Если у неё кончился лимит или она
#    сломалась, ставим её на паузу и берём следующую.
# 5. Отправляем ответ обычным текстом (ВК не показывает разметку).
#
# Памяти между разговорами нет: только переписка из ВК. Фото, голосовые и файлы не разбираются.
import os, json, time, hashlib, random, re, threading, datetime
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

PORT = int(os.environ.get('PORT', '3400'))
VK_TOKEN = os.environ.get('VK_GROUP_TOKEN', '').strip()
VK_V = '5.199'
VK_SCREEN = os.environ.get('VK_GROUP_SCREEN_NAME', 'namelessdhamma').lstrip('@')
PUBLIC_BASE = (os.environ.get('VK_PUBLIC_BASE_URL') or os.environ.get('RENDER_EXTERNAL_URL') or '').strip().rstrip('/')
ALLOWED = {int(x) for x in os.environ.get('VK_ALLOWED_USER_IDS', '').replace(' ', '').split(',') if x.isdigit()}
GROQ_KEY = os.environ.get('GROQ_API_KEY', '').strip()
CF_ACCOUNT = os.environ.get('CLOUDFLARE_ACCOUNT_ID', '').strip()
CF_TOKEN = os.environ.get('CLOUDFLARE_API_TOKEN', '').strip()
OPENROUTER_KEY = os.environ.get('OPENROUTER_API_KEY', '').strip()

CALLBACK_PATH = '/vk/callback/' + hashlib.sha256(('nd-vk-path:' + VK_TOKEN).encode()).hexdigest()[:32]
CALLBACK_URL = PUBLIC_BASE + CALLBACK_PATH if PUBLIC_BASE else ''

DEBOUNCE = 4            # секунд тишины, после которых отвечаем
HISTORY_MESSAGES = 10   # сколько последних сообщений видит модель
FULL_MESSAGES = 4       # из них самые свежие идут почти целиком...
FULL_CHARS = 2500       # ...до стольких знаков каждое,
SHORT_CHARS = 500       # а более старые сжимаются до стольких знаков
TOTAL_CHARS = 9000      # вся переписка не длиннее этого: лишние старые сообщения отбрасываем
MAX_ANSWER_TOKENS = 1500  # моделям, которые сначала думают, даём ещё 2000 на раздумья ('thinks')
CF_DAILY_NEURONS = 9000  # бесплатно 10 000 в сутки; держим запас, чтобы никогда не платить
# Счётчик нейронов Cloudflare хранится в файле, чтобы не обнуляться при перезапуске.
CF_FILE = os.path.join(os.path.dirname(os.environ.get('PORFIRCHIK_MEMOS_LOCAL_DB', '')) or '.',
                       'porfirchik-cloudflare-neurons.json')

# Модели от сильной к слабой. Сила = рейтинг Arena по русскому языку (arena.ai/leaderboard/text/russian,
# 6 ноября 2026): он мерит сразу и ум модели, и её русский. Слабее ~1380 не берём.
# Все модели бесплатные. OpenRouter только с нулевым хранением данных (zdr) и нулевой ценой.
# cf_in/cf_out: сколько "нейронов" Cloudflare стоит миллион токенов (для бесплатного суточного лимита).
POOL = [
    {'router': 'openrouter', 'model': 'google/gemma-4-31b-it:free', 'arena_ru': 1468},
    {'router': 'cloudflare', 'model': '@cf/google/gemma-4-26b-a4b-it', 'arena_ru': 1438, 'cf_in': 9091, 'cf_out': 27273},
    {'router': 'groq', 'model': 'qwen/qwen3.8-27b', 'arena_ru': 1411, 'thinks': True,
     'extra': {'reasoning_effort': 'default'}},
    {'router': 'groq', 'model': 'minimaxai/minimax-m2.7', 'arena_ru': 1404, 'thinks': True},
    {'router': 'openrouter', 'model': 'nvidia/nemotron-3-ultra-550b-a55b:free', 'arena_ru': 1402, 'thinks': True},
    {'router': 'groq', 'model': 'openai/gpt-oss-120b', 'arena_ru': 1390, 'thinks': True,  # ниже 155-го места, оценка
     'extra': {'reasoning_effort': 'medium', 'include_reasoning': False}},
    {'router': 'cloudflare', 'model': '@cf/openai/gpt-oss-120b', 'arena_ru': 1390, 'thinks': True,
     'cf_in': 31818, 'cf_out': 68182, 'extra': {'reasoning_effort': 'medium'}},
]

ROUTERS = {
    'groq': {'url': 'https://api.groq.com/openai/v1/chat/completions', 'key': GROQ_KEY,
             'max_field': 'max_completion_tokens'},
    'cloudflare': {'url': 'https://api.cloudflare.com/client/v4/accounts/%s/ai/v1/chat/completions' % CF_ACCOUNT,
                   'key': CF_TOKEN if CF_ACCOUNT else '', 'max_field': 'max_tokens'},
    'openrouter': {'url': 'https://openrouter.ai/api/v1/chat/completions', 'key': OPENROUTER_KEY,
                   'max_field': 'max_tokens',
                   'headers': {'HTTP-Referer': 'https://namelessdhamma.org', 'X-Title': 'ND Porfirchik'},
                   'extra': {'reasoning': {'exclude': True},
                             'provider': {'zdr': True, 'data_collection': 'deny',
                                          'max_price': {'prompt': 0, 'completion': 0}}}},
}

state = {'phase': 'starting', 'version': 'porfirchik-v21', 'group_id': None,
         'callback_server_id': None, 'last_answer': None, 'last_error': None, 'cloudflare_counter_saved': None}
cooldown_until = {}            # модель -> время, до которого её не трогаем
last_error = {}                # модель -> последняя ошибка
cf_spent = {'day': '', 'neurons': 0.0}
answered_upto = {}             # собеседник -> id его последнего сообщения, на которое уже ответили
seen_events, seen_order = set(), []
timers, peer_locks = {}, {}
lock = threading.Lock()


def log(tag, **data):
    print(tag, json.dumps(data, ensure_ascii=False), flush=True)


def clean_error(e):
    s = str(e)
    for secret in (VK_TOKEN, GROQ_KEY, CF_TOKEN, OPENROUTER_KEY, CF_ACCOUNT, CALLBACK_PATH[13:]):
        if secret:
            s = s.replace(secret, '[скрыто]')
    return s[:500]


# ---------- ВКонтакте ----------

def vk(method, params=None):
    q = dict(params or {}, access_token=VK_TOKEN, v=VK_V)
    req = Request('https://api.vk.com/method/' + method, data=urlencode(q).encode(), method='POST')
    with urlopen(req, timeout=20) as r:
        j = json.loads(r.read().decode())
    if 'error' in j:
        raise RuntimeError('VK %s: %s %s' % (method, j['error'].get('error_code'), j['error'].get('error_msg')))
    return j.get('response')


def register():
    if not CALLBACK_URL:
        raise RuntimeError('нет VK_PUBLIC_BASE_URL')
    r = vk('groups.getById', {'group_ids': VK_SCREEN})
    groups = r.get('groups') if isinstance(r, dict) else r
    gid = int(groups[0]['id'])
    state['group_id'] = gid
    items = vk('groups.getCallbackServers', {'group_id': gid}).get('items') or []
    sid = next((int(s['id']) for s in items if (s.get('url') or '').rstrip('/') == CALLBACK_URL), None)
    if sid is None:
        sid = int(vk('groups.addCallbackServer', {'group_id': gid, 'url': CALLBACK_URL, 'title': 'Porfirchik'})['server_id'])
    vk('groups.setCallbackSettings', {'group_id': gid, 'server_id': sid, 'api_version': VK_V, 'message_new': 1})
    state['callback_server_id'] = sid


def startup():
    if not VK_TOKEN:
        state['phase'] = 'waiting_for_token'
        return
    wait = 5
    while True:
        try:
            register()
            state['phase'] = 'ready'
            log('PORFIRCHIK_READY', group_id=state['group_id'], server_id=state['callback_server_id'],
                models=[m['model'] for m in POOL if ROUTERS[m['router']]['key']])
            return
        except Exception as e:
            state['phase'] = 'retrying'
            state['last_error'] = clean_error(e)
            log('VK_REGISTER_RETRY', error=state['last_error'], wait=wait)
            time.sleep(wait)
            wait = min(wait * 2, 300)


def send(peer, text):
    parts = []
    while len(text) > 3900:
        cut = text.rfind('\n', 0, 3900)
        if cut < 2000:
            cut = text.rfind(' ', 0, 3900)
        if cut < 2000:
            cut = 3900
        parts.append(text[:cut].strip())
        text = text[cut:].strip()
    parts.append(text)
    for part in parts:
        if part:
            vk('messages.send', {'peer_id': peer, 'random_id': random.randint(1, 2 ** 31 - 1), 'message': part})


# ---------- Переписка -> сообщения для модели ----------

ATTACHMENT_NAMES = {'photo': 'фото', 'audio_message': 'голосовое сообщение', 'video': 'видео',
                    'sticker': 'стикер', 'graffiti': 'граффити', 'audio': 'музыка', 'gift': 'подарок',
                    'poll': 'опрос', 'market': 'товар', 'story': 'история'}


def message_text(m):
    """Текст сообщения ВК с пометками о вложениях и пересланных сообщениях."""
    parts = [(m.get('text') or '').strip()]
    for a in m.get('attachments') or []:
        t = a.get('type')
        obj = a.get(t) or {}
        if t == 'doc':
            parts.append('[файл: %s]' % (obj.get('title') or 'без названия'))
        elif t == 'link':
            parts.append('[ссылка: %s %s]' % (obj.get('title') or '', obj.get('url') or ''))
        elif t == 'wall':
            parts.append('[запись со стены: %s]' % (obj.get('text') or '')[:SHORT_CHARS])
        else:
            parts.append('[%s]' % ATTACHMENT_NAMES.get(t, 'вложение'))
    quoted = ([m['reply_message']] if m.get('reply_message') else []) + (m.get('fwd_messages') or [])[:3]
    for q in quoted:
        parts.append('[цитата: %s]' % ((q.get('text') or '').strip()[:SHORT_CHARS] or 'без текста'))
    return '\n'.join(p for p in parts if p)


def shorten(text, limit):
    if len(text) <= limit:
        return text
    head = int(limit * 0.7)
    return text[:head].rstrip() + ' […] ' + text[-(limit - head):].lstrip()


def conversation(peer):
    """Последние HISTORY_MESSAGES сообщений диалога в виде ролей user/assistant, от старых к новым.
    Возвращает (turns, newest): newest — id самого свежего сообщения собеседника.
    Если на всё уже ответили, turns пуст."""
    items = vk('messages.getHistory', {'peer_id': peer, 'count': HISTORY_MESSAGES}).get('items') or []
    items.reverse()
    mine = lambda m: int(m.get('from_id') or 0) < 0
    done = answered_upto.get(peer)
    if done is None:
        # после перезапуска не знаем, на что уже ответили: отвечаем, если последнее слово за собеседником
        if not items or mine(items[-1]):
            return [], None
    else:
        new_ids = {m.get('id') for m in items if not mine(m) and int(m.get('id') or 0) > done}
        if not new_ids:
            return [], None
        # что пришло, пока бот писал прошлый ответ, ставим после этого ответа
        items = [m for m in items if m.get('id') not in new_ids] + [m for m in items if m.get('id') in new_ids]
    newest = max(int(m.get('id') or 0) for m in items if not mine(m))
    turns = []
    for i, m in enumerate(items):
        role = 'assistant' if mine(m) else 'user'
        text = message_text(m) or '[пустое сообщение]'
        text = shorten(text, FULL_CHARS if i >= len(items) - FULL_MESSAGES else SHORT_CHARS)
        if turns and turns[-1]['role'] == role:
            turns[-1]['content'] += '\n\n' + text
        else:
            turns.append({'role': role, 'content': text})
    while len(turns) > 1 and sum(len(t['content']) for t in turns) > TOTAL_CHARS:
        turns.pop(0)
    while turns and turns[0]['role'] == 'assistant':
        turns.pop(0)
    return turns, newest


SYSTEM_PROMPT = '''Ты Порфирчик, собеседник в личных сообщениях сообщества Nameless Dhamma во ВКонтакте. Сейчас {now} по Москве.

Перед ответом перечитай всю переписку и пойми, о чём идёт разговор. Отвечай на последнее сообщение собеседника, но с учётом предыдущих. Короткие реплики вроде «а почему?», «дальше», «а он?», «да» почти всегда продолжают прошлую тему: пойми из переписки, к чему они относятся. Если собеседник прислал несколько сообщений подряд, ответь на них вместе. Если и по переписке непонятно, чего он хочет, задай один короткий уточняющий вопрос вместо догадки.

Пиши на языке собеседника, обычно по-русски: живым, грамотным, простым языком, как образованный человек в переписке. Без канцелярита, без кальки с английского. Длина по делу: на простой вопрос хватит пары фраз, на сложный дай развёрнутый ответ.

Будь честным. Не выдумывай факты, цитаты, названия, ссылки и цифры. Если не знаешь или не уверен, так и скажи. Интернета у тебя нет, свежих новостей ты не знаешь. Твои знания заканчиваются на дате обучения, поэтому о последних событиях говори осторожно. Если собеседник поправляет тебя по делу, признай ошибку и исправься. Если он ошибается, скажи об этом мягко и прямо.

Фото, голосовые сообщения, видео и файлы ты пока не видишь и не слышишь: в переписке они отмечены в квадратных скобках, например [фото]. Если собеседник прислал такое без текста, коротко скажи, что пока не можешь это посмотреть или послушать, и попроси написать словами. Не притворяйся, что видел содержимое.

ВКонтакте не показывает разметку. Не используй звёздочки, решётки, таблицы и код в обратных кавычках. Списки делай через цифры или тире, абзацы разделяй пустой строкой.

Памяти о прошлых разговорах у тебя нет: ты видишь только последние сообщения этого диалога. Если спросят, кто ты, скажи, что ты языковая модель, которая отвечает через сервис Nameless Dhamma.

Когда речь о буддизме, Дхамме, медитации или палийских текстах, опирайся на тхераваду и ранний палийский канон: точно объясняй палийские термины и при необходимости указывай источник (например, MN 10). Другие традиции излагай точно и нейтрально, если о них спрашивают. На вопросы на любые другие темы отвечай обычно, не сводя их к буддизму.'''


def system_prompt():
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))
    months = ['января', 'февраля', 'марта', 'апреля', 'мая', 'июня', 'июля', 'августа',
              'сентября', 'октября', 'ноября', 'декабря']
    return SYSTEM_PROMPT.format(now='%d %s %d года, %02d:%02d' % (now.day, months[now.month - 1], now.year,
                                                                 now.hour, now.minute))


def plain_text(text):
    """Убирает скрытые рассуждения и разметку, которую ВК не показывает."""
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.S | re.I)
    text = re.sub(r'^.*?</think>', '', text, flags=re.S | re.I)
    text = re.sub(r'<think>.*', '', text, flags=re.S | re.I)  # раздумья оборвались без конца: ответа нет
    text = re.sub(r'```[a-zA-Z]*\n?', '', text)
    text = re.sub(r'^\s{0,3}#{1,6}\s*', '', text, flags=re.M)
    text = re.sub(r'\[([^\]\n]+)\]\((https?://[^)\s]+)\)', r'\1 (\2)', text)
    text = text.replace('**', '').replace('__', '').replace('`', '')
    text = re.sub(r'^(\s*)\* ', r'\1– ', text, flags=re.M)
    text = re.sub(r'(?<![\w*])\*(\S[^*\n]*?)\*(?![\w*])', r'\1', text)
    return re.sub(r'\n{3,}', '\n\n', text).strip()


# ---------- Модели ----------

def next_utc_midnight():
    return (int(time.time()) // 86400 + 1) * 86400


def pause_for(code, body, retry_after):
    """На сколько секунд выключить модель после ошибки."""
    b = body.lower()
    if 'per-day' in b or 'per day' in b or 'daily' in b or '"code":4006' in b.replace(' ', ''):
        return next_utc_midnight() - time.time()      # суточный лимит (4006 — код Cloudflare)
    if code == 429:
        return max(60, min(retry_after or 60, 3600))  # минутный лимит
    if code in (401, 402, 403, 404):
        return 6 * 3600                               # нет доступа, модель убрали или нет бесплатной/приватной
    if code in (400, 413, 422):
        return 1800                                   # модель не принимает такой запрос
    return 120                                        # сбой или таймаут


# Нейроны Cloudflare. Перед вызовом резервируем худший случай, после вызова ставим настоящий расход.
# Так даже одновременные ответы не превысят суточный предел. Вызывать под lock.

def cf_today():
    day = time.strftime('%Y-%m-%d', time.gmtime())
    if cf_spent['day'] != day:
        cf_spent.update(day=day, neurons=0.0)
    return cf_spent


def cf_save():
    try:
        os.makedirs(os.path.dirname(CF_FILE) or '.', exist_ok=True)
        with open(CF_FILE + '.tmp', 'w') as f:
            json.dump(cf_spent, f)
        os.replace(CF_FILE + '.tmp', CF_FILE)
        state['cloudflare_counter_saved'] = True
    except OSError as e:
        state['cloudflare_counter_saved'] = False
        log('CF_SAVE_FAILED', error=clean_error(e))


def cf_load():
    try:
        with open(CF_FILE) as f:
            saved = json.load(f)
        cf_spent.update(day=str(saved['day']), neurons=float(saved['neurons']))
    except (OSError, ValueError, KeyError, TypeError):
        pass


def max_tokens(m):
    return MAX_ANSWER_TOKENS + (2000 if m.get('thinks') else 0)


def cf_cost(m, prompt_tokens, completion_tokens):
    return (prompt_tokens * m['cf_in'] + completion_tokens * m['cf_out']) / 1e6


def cf_reserve(m, messages):
    """Сколько нейронов отложено на вызов: 0 не для Cloudflare, None если суточный предел не позволяет."""
    if m['router'] != 'cloudflare':
        return 0
    chars = sum(len(x['content']) for x in messages)
    worst = cf_cost(m, chars / 2, max_tokens(m))
    with lock:
        if cf_today()['neurons'] + worst > CF_DAILY_NEURONS:
            return None
        cf_spent['neurons'] += worst
        cf_save()
    return worst


def cf_settle(reserved, spent):
    """Заменяет резерв настоящим расходом. spent=None: расход неизвестен, резерв остаётся."""
    if not reserved or spent is None:
        return
    with lock:
        cf_today()['neurons'] = max(0.0, cf_spent['neurons'] - reserved + spent)
        cf_save()


def available(m):
    return bool(ROUTERS[m['router']]['key']) and cooldown_until.get(m['model'], 0) <= time.time()


def call_model(m, messages):
    """Возвращает (текст, расход нейронов Cloudflare или None, если модель его не сообщила)."""
    r = ROUTERS[m['router']]
    payload = {'model': m['model'], 'messages': messages, 'temperature': 0.6,
               r['max_field']: max_tokens(m)}
    payload.update(r.get('extra', {}))
    payload.update(m.get('extra', {}))
    headers = {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + r['key']}
    headers.update(r.get('headers', {}))
    req = Request(r['url'], data=json.dumps(payload, ensure_ascii=False).encode(), headers=headers, method='POST')
    with urlopen(req, timeout=90) as resp:
        j = json.loads(resp.read().decode())
    u = j.get('usage') or {}
    spent = None
    if m['router'] == 'cloudflare' and 'prompt_tokens' in u:
        spent = cf_cost(m, u.get('prompt_tokens') or 0, u.get('completion_tokens') or 0)
    text = plain_text(((j.get('choices') or [{}])[0].get('message') or {}).get('content') or '')
    return text, spent


def answer(messages):
    """Спрашивает модели по очереди, от сильной к слабой, пока одна не ответит."""
    for m in POOL:
        if not available(m):
            continue
        reserved = cf_reserve(m, messages)
        if reserved is None:
            continue
        started, spent = time.time(), None
        try:
            text, spent = call_model(m, messages)
            if not text:
                raise RuntimeError('пустой ответ')
            state['last_answer'] = {'model': m['model'], 'seconds': round(time.time() - started, 1),
                                    'at': int(time.time())}
            log('ANSWERED', **state['last_answer'])
            return text
        except HTTPError as e:
            spent = 0  # запрос отклонён, нейроны не списаны
            try:
                body = e.read().decode('utf-8', 'replace')
            except Exception:
                body = ''
            ra = (e.headers.get('retry-after') or '') if e.headers else ''
            pause = pause_for(e.code, body, int(ra) if ra.isdigit() else 0)
            err = 'HTTP %s: %s' % (e.code, clean_error(body))
        except Exception as e:
            pause, err = 120, clean_error(e)
        finally:
            cf_settle(reserved, spent)
        cooldown_until[m['model']] = time.time() + pause
        last_error[m['model']] = err[:120]
        log('MODEL_FAILED', model=m['model'], pause_minutes=round(pause / 60), error=err)
    return None


# ---------- Обработка сообщений ----------

def reply(peer):
    with peer_locks.setdefault(peer, threading.Lock()):
        try:
            turns, newest = conversation(peer)
            if not turns:
                return  # на все сообщения уже ответили
            try:
                vk('messages.setActivity', {'peer_id': peer, 'type': 'typing'})
            except Exception:
                pass
            text = answer([{'role': 'system', 'content': system_prompt()}] + turns)
            send(peer, text or 'Сейчас все мои модели заняты или исчерпали дневной лимит. Напишите, пожалуйста, чуть позже.')
            answered_upto[peer] = newest
        except Exception as e:
            state['last_error'] = clean_error(e)
            log('REPLY_ERROR', error=state['last_error'])


def on_message(m):
    peer, uid = int(m.get('peer_id') or 0), int(m.get('from_id') or 0)
    if uid <= 0 or peer != uid:
        return  # отвечаем только в личных сообщениях людям
    if ALLOWED and uid not in ALLOWED:
        send(peer, 'Этот собеседник пока открыт не для всех.')
        return
    with lock:
        if peer in timers:
            timers[peer].cancel()
        timers[peer] = threading.Timer(DEBOUNCE, reply, args=(peer,))
        timers[peer].daemon = True
        timers[peer].start()


def first_time(event_id):
    """ВК может прислать одно событие дважды; второй раз его пропускаем."""
    if not event_id:
        return True
    with lock:
        if event_id in seen_events:
            return False
        seen_events.add(event_id)
        seen_order.append(event_id)
        if len(seen_order) > 1000:
            seen_events.discard(seen_order.pop(0))
        return True


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def respond(self, code, body):
        raw = (json.dumps(body, ensure_ascii=False) if isinstance(body, dict) else body).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8' if isinstance(body, dict) else 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        if self.path.split('?')[0] != '/health':
            return self.respond(404, 'not found')
        now = time.time()
        models = [{'router': m['router'], 'model': m['model'], 'arena_ru': m['arena_ru'],
                   'key': bool(ROUTERS[m['router']]['key']),
                   'paused_minutes': max(0, round((cooldown_until.get(m['model'], 0) - now) / 60)),
                   'last_error': last_error.get(m['model'])} for m in POOL]
        with lock:
            neurons = round(cf_today()['neurons'])
        self.respond(200, dict(state, models=models, cloudflare_neurons_today=neurons))

    def do_POST(self):
        if self.path.split('?')[0] != CALLBACK_PATH or not VK_TOKEN:
            return self.respond(404, 'not found')
        try:
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
            gid = int(body.get('group_id') or 0)
        except Exception:
            return self.respond(400, 'bad request')
        if state['group_id'] and gid and gid != state['group_id']:
            return self.respond(403, 'forbidden')
        if body.get('type') == 'confirmation':
            try:
                return self.respond(200, vk('groups.getCallbackConfirmationCode', {'group_id': gid or state['group_id']})['code'])
            except Exception as e:
                state['last_error'] = clean_error(e)
                return self.respond(500, 'error')
        self.respond(200, 'ok')
        if body.get('type') == 'message_new' and first_time(body.get('event_id')):
            obj = body.get('object') or {}
            try:
                on_message(obj.get('message') or obj)
            except Exception as e:
                state['last_error'] = clean_error(e)
                log('MESSAGE_ERROR', error=state['last_error'])


if __name__ == '__main__':
    cf_load()
    threading.Thread(target=startup, daemon=True).start()
    log('PORFIRCHIK_START', port=PORT, version=state['version'])
    ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
