const RAILWAY_CALLBACK =
  "https://nd-external-intelligence-production.up.railway.app/drive/oauth/callback";

function page(title: string, detail: string, ok: boolean) {
  const color = ok ? "#2e7d32" : "#b3261e";
  return new Response(
    `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title></head><body style="font-family:system-ui,sans-serif;max-width:720px;margin:64px auto;padding:0 20px"><h1 style="color:${color}">${title}</h1><p>${detail}</p><p>You can close this page and return to ChatGPT.</p></body></html>`,
    { status: ok ? 200 : 502, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } },
  );
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const code = url.searchParams.get("code");
  const state = url.searchParams.get("state");
  const error = url.searchParams.get("error");
  if ((!code && !error) || !state) {
    return page("Drive authorization failed", "Google returned an incomplete OAuth callback.", false);
  }

  try {
    const response = await fetch(RAILWAY_CALLBACK, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ code, state, error }),
      cache: "no-store",
    });
    const body = await response.json().catch(() => ({}));
    if (!response.ok || !body?.ok) {
      const reason = String(body?.error ?? `HTTP ${response.status}`).slice(0, 240);
      return page("Drive authorization failed", reason, false);
    }
    return page("ND Drive Backup authorized", "The user OAuth credential was stored encrypted and verified server-side.", true);
  } catch (error) {
    const detail = error instanceof Error ? error.message : "unknown_error";
    return page("Drive authorization failed", detail.slice(0, 240), false);
  }
}
