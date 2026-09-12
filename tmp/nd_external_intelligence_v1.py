import asyncio
import hmac
import os
import uuid
from typing import Literal, Optional

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

SERVICE_NAME = "nd-external-intelligence"
PROVIDER = "zai"
MODEL = os.getenv("ZAI_MODEL", "glm-5.3-flash")
BASE_URL = os.getenv("ZAI_BASE_URL", "https://api.z.ai/api/paas/v4").rstrip("/")
ZAI_API_KEY = os.getenv("ZAI_API_KEY", "")
SHARED_TOKEN = os.getenv("ND_EAI_SHARED_TOKEN", "")

ROLE_PROMPTS = {
    "critic": (
        "You are an independent auxiliary critic for Nameless Dhamma. "
        "Find concrete weaknesses, hidden assumptions, likely failures, and better alternatives. "
        "Be concise and evidence-oriented. You are advisory only and have no authority or tool access."
    ),
    "reviewer": (
        "You are an independent software reviewer for Nameless Dhamma. "
        "Inspect the supplied code or diff for correctness, security, reliability, maintainability, "
        "edge cases, and missing tests. Prioritize actionable defects over style commentary. "
        "You are advisory only and have no authority or tool access."
    ),
    "coder": (
        "You are an auxiliary coding model for Nameless Dhamma. "
        "Produce the smallest correct implementation or patch that satisfies the request. "
        "State assumptions and include tests when useful. Do not invent access to tools or secrets. "
        "Your output is a proposal that must be verified by the controlling GPT/True Developer."
    ),
    "agent_planner": (
        "You are an independent agent-plan critic for Nameless Dhamma. "
        "Evaluate the proposed plan for unsafe authority expansion, missing failure handling, "
        "unnecessary complexity, cost, resumability, and verification gaps. "
        "Return bounded recommendations only; you have no authority or tool access."
    ),
}


class InvokeRequest(BaseModel):
    task: str = Field(min_length=1, max_length=120_000)
    role: Literal["critic", "reviewer", "coder", "agent_planner"] = "critic"
    context: Optional[str] = Field(default=None, max_length=240_000)
    max_tokens: int = Field(default=4096, ge=256, le=16384)
    temperature: float = Field(default=0.2, ge=0.0, le=1.5)
    thinking: bool = True


def require_auth(authorization: Optional[str] = Header(default=None)) -> None:
    if not SHARED_TOKEN:
        raise HTTPException(status_code=503, detail="adapter_not_configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing_bearer_token")
    supplied = authorization[7:]
    if not hmac.compare_digest(supplied, SHARED_TOKEN):
        raise HTTPException(status_code=403, detail="invalid_token")


app = FastAPI(title="ND External Intelligence Adapter", version="0.1.0")


@app.get("/health")
async def health():
    return {
        "service": SERVICE_NAME,
        "status": "ok",
        "provider": PROVIDER,
        "model": MODEL,
        "configured": bool(ZAI_API_KEY and SHARED_TOKEN),
        "authority": "advisory_only",
    }


@app.get("/v1/capabilities", dependencies=[Depends(require_auth)])
async def capabilities():
    return {
        "provider": PROVIDER,
        "model": MODEL,
        "roles": list(ROLE_PROMPTS),
        "tool_access": False,
        "write_authority": False,
        "provider_override": False,
        "model_override": False,
    }


@app.post("/v1/invoke", dependencies=[Depends(require_auth)])
async def invoke(req: InvokeRequest):
    if not ZAI_API_KEY:
        raise HTTPException(status_code=503, detail="zai_api_key_not_configured")

    request_id = str(uuid.uuid4())
    user_content = req.task
    if req.context:
        user_content = f"CONTEXT:\n{req.context}\n\nTASK:\n{req.task}"

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": ROLE_PROMPTS[req.role]},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
        "max_tokens": req.max_tokens,
        "temperature": req.temperature,
        "thinking": {"type": "enabled" if req.thinking else "disabled"},
    }

    headers = {
        "Authorization": f"Bearer {ZAI_API_KEY}",
        "Content-Type": "application/json",
        "Accept-Language": "en-US,en",
    }

    last_error = None
    timeout = httpx.Timeout(120.0, connect=15.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(3):
            try:
                response = await client.post(
                    f"{BASE_URL}/chat/completions",
                    headers=headers,
                    json=payload,
                )
                if response.status_code == 429 or response.status_code >= 500:
                    last_error = f"upstream_{response.status_code}"
                    if attempt < 2:
                        await asyncio.sleep(1.5 * (2 ** attempt))
                        continue
                response.raise_for_status()
                data = response.json()
                choice = data.get("choices", [{}])[0]
                message = choice.get("message", {})
                return {
                    "request_id": request_id,
                    "provider": PROVIDER,
                    "model": data.get("model", MODEL),
                    "role": req.role,
                    "content": message.get("content", ""),
                    "reasoning_content": message.get("reasoning_content"),
                    "finish_reason": choice.get("finish_reason"),
                    "usage": data.get("usage", {}),
                    "authority": "advisory_only",
                }
            except httpx.HTTPStatusError as exc:
                detail = f"upstream_http_{exc.response.status_code}"
                raise HTTPException(status_code=502, detail=detail) from exc
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc.__class__.__name__
                if attempt < 2:
                    await asyncio.sleep(1.5 * (2 ** attempt))
                    continue

    raise HTTPException(status_code=502, detail=f"upstream_unavailable:{last_error or 'unknown'}")
