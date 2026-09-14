export const config = { runtime: 'nodejs' };

function json(res, code, body) {
  res.status(code).json(body);
}

function authOk(req) {
  const token = (process.env.ND_VK_MCP_ROUTE_TOKEN || '').trim();
  return Boolean(token) && String(req.headers.authorization || '') === `Bearer ${token}`;
}

async function probe(provider) {
  let key, model, url, headers;
  if (provider === 'groq') {
    key = (process.env.GROQ_API_KEY || '').trim();
    model = (process.env.GROQ_MODEL || 'openai/gpt-oss-120b').trim();
    url = 'https://api.groq.com/openai/v1/chat/completions';
    headers = { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' };
  } else if (provider === 'openrouter') {
    key = (process.env.OPENROUTER_API_KEY || process.env.OpenRouter || '').trim();
    model = (process.env.OPENROUTER_MODEL || 'openrouter/free').trim();
    url = 'https://openrouter.ai/api/v1/chat/completions';
    headers = {
      Authorization: `Bearer ${key}`,
      'Content-Type': 'application/json',
      'HTTP-Referer': 'https://namelessdhamma.org',
      'X-Title': 'ND Router Qualification'
    };
  } else {
    return { code: 400, body: { ok: false, error: 'provider_must_be_groq_or_openrouter' } };
  }
  if (!key) return { code: 503, body: { ok: false, provider, error: 'provider_not_configured' } };
  const started = Date.now();
  const r = await fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      model,
      messages: [{ role: 'user', content: 'Reply exactly ND_ROUTER_PROBE_OK.' }],
      max_tokens: 32,
      temperature: 0
    })
  });
  const text = await r.text();
  let data;
  try { data = JSON.parse(text); } catch { data = { raw: text.slice(0, 600) }; }
  if (!r.ok) return { code: r.status, body: { ok: false, provider, error: data, channel: 'vercel' } };
  const reply = String(data?.choices?.[0]?.message?.content || '').trim();
  return {
    code: 200,
    body: {
      ok: reply === 'ND_ROUTER_PROBE_OK',
      provider,
      configured_model: model,
      response_model: data?.model || null,
      reply: reply.slice(0, 120),
      latency_ms: Date.now() - started,
      channel: 'vercel'
    }
  };
}

export default async function handler(req, res) {
  if (!authOk(req)) return json(res, 403, { ok: false, error: 'forbidden' });
  const action = String(req.query?.action || req.body?.action || '').toLowerCase();
  if (req.method === 'GET' && action === 'status') {
    return json(res, 200, {
      ok: true,
      channel: 'vercel',
      adapter: 'nd_vercel_router_control_failover_v1',
      providers: {
        groq: Boolean(process.env.GROQ_API_KEY),
        openrouter: Boolean(process.env.OPENROUTER_API_KEY || process.env.OpenRouter)
      }
    });
  }
  if (req.method === 'GET' && action === 'health') {
    return json(res, 200, { ok: true, channel: 'vercel' });
  }
  if (req.method === 'POST' && action === 'request') {
    try {
      const out = await probe(String(req.body?.provider || '').toLowerCase());
      return json(res, out.code, out.body);
    } catch (e) {
      return json(res, 502, { ok: false, error: String(e?.message || e).slice(0, 600), channel: 'vercel' });
    }
  }
  return json(res, 404, { ok: false, error: 'not_found' });
}
