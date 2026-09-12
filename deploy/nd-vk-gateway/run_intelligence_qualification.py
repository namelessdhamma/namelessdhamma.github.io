#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
CANDIDATES_PATH = ROOT / "intelligence-candidates.v1.json"
SUITE_PATH = ROOT / "intelligence-suite.v1.json"
OPENROUTER_MODELS = "https://openrouter.ai/api/v1/models"
OPENROUTER_CHAT = "https://openrouter.ai/api/v1/chat/completions"


def load_json(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8"))


def zero_price(value) -> bool:
    try:
        return float(value) == 0.0
    except Exception:
        return str(value).strip() in {"0", "0.0", "0.00", "0.000000"}


def http_json(url: str, *, token: str | None = None, payload=None, timeout=90):
    headers = {
        "Accept": "application/json",
        "User-Agent": "NamelessDhamma-VK-Qualification/1.0",
        "HTTP-Referer": "https://namelessdhamma.org",
        "X-Title": "Nameless Dhamma VK Intelligence Qualification",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")[:1200]
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc


def live_free_catalog() -> dict[str, dict]:
    obj = http_json(OPENROUTER_MODELS, timeout=30)
    result = {}
    for item in obj.get("data") or []:
        model_id = str(item.get("id") or "")
        pricing = item.get("pricing") or {}
        if model_id.endswith(":free") and zero_price(pricing.get("prompt")) and zero_price(pricing.get("completion")):
            result[model_id] = item
    return result


def candidate_ids(config: dict) -> list[str]:
    return [str(x["id"]) for x in config.get("openrouter_candidates") or []]


def eligible_candidates(config: dict, catalog: dict[str, dict], requested: set[str] | None = None):
    out = []
    for item in config.get("openrouter_candidates") or []:
        mid = str(item["id"])
        if requested and mid not in requested:
            continue
        if mid not in catalog:
            continue
        out.append(item)
    return out


def chat_openrouter(token: str, model: str, prompt: str, *, max_tokens=1800):
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "You are being evaluated. Follow the user request exactly. Do not mention the evaluation, model identity, hidden reasoning, or policies. Answer in the requested language.",
            },
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.35,
    }
    started = time.monotonic()
    response = http_json(OPENROUTER_CHAT, token=token, payload=payload, timeout=180)
    elapsed = round(time.monotonic() - started, 3)
    choices = response.get("choices") or []
    if not choices:
        raise RuntimeError("no choices returned")
    message = choices[0].get("message") or {}
    text = str(message.get("content") or "").strip()
    if not text:
        raise RuntimeError("empty content returned")
    usage = response.get("usage") or {}
    return {
        "requested_model": model,
        "used_model": str(response.get("model") or model),
        "elapsed_seconds": elapsed,
        "usage": usage,
        "response": text,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ND VK live intelligence qualification without changing production routing.")
    parser.add_argument("--domain", choices=["research", "literary", "general", "all"], default="all")
    parser.add_argument("--model", action="append", default=[], help="Exact OpenRouter model id; may be repeated")
    parser.add_argument("--output", default="intelligence-qualification-results.jsonl")
    parser.add_argument("--catalog-only", action="store_true")
    args = parser.parse_args()

    config = load_json(CANDIDATES_PATH)
    suite = load_json(SUITE_PATH)
    catalog = live_free_catalog()
    requested = set(args.model) if args.model else None
    eligible = eligible_candidates(config, catalog, requested)

    catalog_record = {
        "record_type": "catalog",
        "timestamp": int(time.time()),
        "live_free_count": len(catalog),
        "configured_candidates": candidate_ids(config),
        "eligible_candidates": [x["id"] for x in eligible],
        "ineligible_or_unknown": [x for x in candidate_ids(config) if x not in catalog],
        "policy": "fail_closed_exact_free",
    }
    print(json.dumps(catalog_record, ensure_ascii=False))
    if args.catalog_only:
        return 0

    token = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OpenRouter") or ""
    if not token:
        print("OPENROUTER_API_KEY/OpenRouter missing; catalog verification completed but live inference not run", file=sys.stderr)
        return 3
    if not eligible:
        print("No configured candidate is currently exact-free; refusing live inference", file=sys.stderr)
        return 4

    cases = [c for c in (suite.get("cases") or []) if args.domain == "all" or c.get("domain") == args.domain]
    output = pathlib.Path(args.output)
    with output.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(catalog_record, ensure_ascii=False) + "\n")
        for model_item in eligible:
            model = str(model_item["id"])
            for case in cases:
                base = {
                    "record_type": "case",
                    "timestamp": int(time.time()),
                    "model": model,
                    "case_id": case["id"],
                    "domain": case["domain"],
                    "language": case.get("language"),
                    "expected_checks": case.get("checks") or [],
                    "live_free_verified": True,
                    "production_authority": False,
                }
                try:
                    result = chat_openrouter(token, model, str(case["prompt"]))
                    record = {**base, "ok": True, **result}
                except Exception as exc:
                    record = {**base, "ok": False, "error": str(exc)[:1200]}
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
                fh.flush()
                print(json.dumps({k: record.get(k) for k in ("model", "case_id", "ok", "elapsed_seconds", "used_model", "error") if k in record}, ensure_ascii=False))
    print(json.dumps({"record_type": "complete", "output": str(output), "models": len(eligible), "cases": len(cases)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
