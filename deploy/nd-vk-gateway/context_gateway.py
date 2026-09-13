"""Production-candidate dispatch bridge for the VK bounded context system.

This module keeps one physical VK chat while automatically selecting logical threads.
It never treats conversation memory as canonical truth. Durable state is stored only in
Father Workspace / Shared Notes through the existing Safe Tool Broker.
"""
from __future__ import annotations

import copy
import json
import threading
from typing import Any, Callable, Dict, Tuple

import context_memory as cm
import context_memory_store as ms

_LOCKS: Dict[str, threading.RLock] = {}
_CACHE: Dict[str, Tuple[Dict[str, Any], ms.FatherWorkspaceMemoryStore]] = {}
_CACHE_GUARD = threading.Lock()


def _user_lock(user_id: str) -> threading.RLock:
    uid = str(user_id)
    with _CACHE_GUARD:
        return _LOCKS.setdefault(uid, threading.RLock())


def reset_process_cache_for_tests() -> None:
    with _CACHE_GUARD:
        _CACHE.clear(); _LOCKS.clear()


def _store_call(broker_invoke: Callable, tool: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    result = broker_invoke(tool, '', payload)
    if not isinstance(result, dict):
        raise ms.MemoryStoreError(f"broker {tool} returned non-object")
    return result


def _discover(user_id: str, broker_invoke: Callable) -> Tuple[Dict[str, Any], ms.FatherWorkspaceMemoryStore]:
    uid = str(user_id)
    def call(tool: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return _store_call(broker_invoke, tool, payload)

    listing = call('sandbox_list', {'folder_id': ms.SHARED_NOTES_FOLDER_ID, 'limit': 100})
    candidates = [x for x in (listing.get('items') or [])
                  if str(x.get('title') or '') == ms.STATE_TITLE and x.get('artifact_id')]
    # The list response intentionally exposes only bounded metadata. Identity lives inside the
    # signed/digested envelope, so discover by exact read+parse rather than by fuzzy title alone.
    for item in candidates:
        store = ms.FatherWorkspaceMemoryStore(call, uid, str(item['artifact_id']))
        try:
            state = store.load()
        except ms.MemoryStoreError:
            continue
        if state is not None and str(state.get('user_id')) == uid:
            return state, store
    return cm.new_state(uid), ms.FatherWorkspaceMemoryStore(call, uid)


def _load(user_id: str, broker_invoke: Callable) -> Tuple[Dict[str, Any], ms.FatherWorkspaceMemoryStore]:
    uid = str(user_id)
    cached = _CACHE.get(uid)
    if cached is not None:
        return cached
    state, store = _discover(uid, broker_invoke)
    _CACHE[uid] = (state, store)
    return state, store


def _mode(mode_by_uid: Dict[Any, str], user_id: Any) -> str:
    raw = str(mode_by_uid.get(user_id, 'auto') or 'auto').lower()
    if raw == 'fast': return 'fast'
    if raw == 'deep': return 'deep'
    return 'default'


def _history(packet: Dict[str, Any]) -> list[Dict[str, str]]:
    # A single provider-agnostic structured block avoids replaying an ever-growing transcript.
    # The selected model receives only the packet built for this logical thread.
    body = json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return [{'role': 'system', 'content': 'ND_BOUNDED_CONTEXT_PACKET_JSON\n' + body}]


def _minimal_clarification() -> str:
    return 'Уточните, пожалуйста, к какой именно предыдущей правке или теме вы хотите вернуться.'


def dispatch(user_id: Any, text: str, event_id: str | None,
             responder: Callable[[Any, str, list[Dict[str, str]]], str],
             history_by_uid: Dict[Any, list], broker_invoke: Callable,
             mode_by_uid: Dict[Any, str]) -> str:
    """Resolve/load → bounded packet → model → durable delta, serialized per VK user.

    `responder` is deliberately provider-neutral. The gateway adapter may point it at any
    currently-qualified strong model/router. The old history dict is used only as a temporary
    compatibility bridge for the legacy router and is always cleared after the call.
    """
    uid = str(user_id)
    query = str(text or 'Продолжи.')
    with _user_lock(uid):
        try:
            state, store = _load(uid, broker_invoke)
        except Exception:
            return 'Сейчас не удалось надёжно восстановить рабочий контекст. Повторите сообщение позже.'

        previous = copy.deepcopy(state)
        packet = cm.build_context_packet(state, query, mode=_mode(mode_by_uid, user_id))
        tid = packet.get('thread_id') or state.get('active_thread_id') or 'general:main'

        if packet.get('needs_clarification'):
            answer = _minimal_clarification()
            cm.add_turn(state, 'user', query, event_id=event_id, thread_id=tid)
            cm.add_turn(state, 'assistant', answer, thread_id=tid)
            try:
                saved = store.save(state, previous if store.artifact_id else None)
                _CACHE[uid] = (state, store)
            except Exception:
                return answer + '\n\nРабочий контекст этой реплики не удалось надёжно сохранить.'
            return answer

        prompt_history = _history(packet)
        # Legacy history exists only for compatibility with the current router implementation.
        # It must never become durable authority or accumulate across requests.
        history_by_uid[user_id] = prompt_history
        try:
            answer = str(responder(user_id, query, prompt_history) or '').strip()
        finally:
            history_by_uid.pop(user_id, None)
        if not answer:
            answer = 'Не удалось сформировать ответ.'

        cm.add_turn(state, 'user', query, event_id=event_id, thread_id=tid)
        cm.add_turn(state, 'assistant', answer, thread_id=tid)
        try:
            store.save(state, previous if store.artifact_id else None)
            _CACHE[uid] = (state, store)
        except Exception:
            # Do not pretend continuity was persisted. The answer itself may still be useful.
            return answer + '\n\nОтвет получен, но рабочий контекст не удалось надёжно сохранить.'
        return answer
