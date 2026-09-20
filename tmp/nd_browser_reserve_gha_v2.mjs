import fs from "node:fs";
import { chromium } from "playwright-core";

const provider = String(process.env.ND_PROVIDER || "").trim().toLowerCase();
const tool = String(process.env.ND_TOOL || "__tools__").trim();
const args = JSON.parse(process.env.ND_ARGUMENTS_JSON || "{}");
const requestKey = String(process.env.ND_REQUEST_KEY || "").trim();

const secrets = {
  lightpanda: String(process.env.LIGHTPANDA_TOKEN || "").trim(),
  cloudflareToken: String(process.env.CLOUDFLARE_API_TOKEN || "").trim(),
  cloudflareAccount: String(process.env.CLOUDFLARE_ACCOUNT_ID || "").trim(),
  apify: String(process.env.APIFY_API_TOKEN || "").trim(),
};

function clean(v) {
  let s = String(v ?? "");
  for (const x of Object.values(secrets)) if (x) s = s.split(x).join("[REDACTED]");
  return s.slice(0, 8000);
}

function save(obj, ok = true) {
  const body = JSON.stringify(obj);
  fs.writeFileSync("nd-internet-failover-result.json", body + "\n");
  if (ok) console.log(body);
  else console.error(body);
}

function ensureHttpUrl(raw) {
  const u = new URL(String(raw || ""));
  if (!["http:", "https:"].includes(u.protocol)) throw new Error("url_must_be_http_or_https");
  return u.toString();
}

async function connectBrowser(kind) {
  if (kind === "lightpanda") {
    if (!secrets.lightpanda) throw new Error("lightpanda_not_configured");
    const endpointURL = "wss://euwest.cloud.lightpanda.io/ws?token=" + encodeURIComponent(secrets.lightpanda);
    const browser = await chromium.connectOverCDP({ endpointURL, timeout: 20000 });
    const context = await browser.newContext({});
    const page = await context.newPage();
    return { browser, context, page, close: async () => {
      try { await page.close(); } catch {}
      try { await context.close(); } catch {}
      try { await browser.close(); } catch {}
    }};
  }
  if (kind === "cloudflare") {
    if (!secrets.cloudflareAccount || !secrets.cloudflareToken) throw new Error("cloudflare_not_configured");
    const endpointURL = "wss://api.cloudflare.com/client/v4/accounts/" +
      encodeURIComponent(secrets.cloudflareAccount) +
      "/browser-rendering/devtools/browser?keep_alive=90000";
    const browser = await chromium.connectOverCDP(endpointURL, {
      headers: { Authorization: "Bearer " + secrets.cloudflareToken },
      timeout: 20000,
    });
    const context = browser.contexts()[0] ?? await browser.newContext();
    const page = context.pages()[0] ?? await context.newPage();
    return { browser, context, page, close: async () => {
      try { await browser.close(); } catch {}
    }};
  }
  throw new Error("unsupported_browser_provider");
}

async function browserSequence(kind, input) {
  const steps = Array.isArray(input.steps) ? input.steps : [];
  if (!steps.length || steps.length > 30) throw new Error("steps_required_max_30");
  const st = await connectBrowser(kind);
  const out = [];
  try {
    for (let i = 0; i < steps.length; i++) {
      const s = steps[i] || {};
      const op = String(s.op || "");
      if (op === "goto") {
        const r = await st.page.goto(ensureHttpUrl(s.url), {
          waitUntil: ["load","domcontentloaded","networkidle","commit"].includes(s.wait_until) ? s.wait_until : "domcontentloaded",
          timeout: Math.min(60000, Math.max(1000, Number(s.timeout_ms || 20000))),
        });
        out.push({ op, ok: true, status: r ? r.status() : null, url: st.page.url(), title: await st.page.title() });
      } else if (op === "get_url") {
        out.push({ op, ok: true, url: st.page.url(), title: await st.page.title() });
      } else if (op === "read_text") {
        const selector = String(s.selector || "body");
        const max = Math.min(50000, Math.max(1, Number(s.max_chars || 12000)));
        const text = await st.page.locator(selector).innerText({ timeout: 15000 });
        out.push({ op, ok: true, selector, text: String(text).slice(0, max), truncated: String(text).length > max });
      } else if (op === "html") {
        const max = Math.min(100000, Math.max(1, Number(s.max_chars || 30000)));
        const html = s.selector
          ? await st.page.locator(String(s.selector)).evaluate(el => el.outerHTML)
          : await st.page.content();
        out.push({ op, ok: true, html: String(html).slice(0, max), truncated: String(html).length > max });
      } else if (op === "click") {
        await st.page.locator(String(s.selector || "")).click({ timeout: 15000 });
        out.push({ op, ok: true, url: st.page.url() });
      } else if (op === "fill") {
        await st.page.locator(String(s.selector || "")).fill(String(s.value ?? ""), { timeout: 15000 });
        out.push({ op, ok: true, selector: String(s.selector || "") });
      } else if (op === "press") {
        const target = s.selector ? st.page.locator(String(s.selector)) : st.page.locator("body");
        await target.press(String(s.key || ""), { timeout: 15000 });
        out.push({ op, ok: true, key: String(s.key || "") });
      } else if (op === "hover") {
        await st.page.locator(String(s.selector || "")).hover({ timeout: 15000 });
        out.push({ op, ok: true });
      } else if (op === "select_option") {
        const selected = await st.page.locator(String(s.selector || "")).selectOption(String(s.value ?? ""), { timeout: 15000 });
        out.push({ op, ok: true, selected });
      } else if (op === "set_checked") {
        await st.page.locator(String(s.selector || "")).setChecked(Boolean(s.checked), { timeout: 15000 });
        out.push({ op, ok: true, checked: Boolean(s.checked) });
      } else if (op === "wait_for_selector") {
        await st.page.locator(String(s.selector || "")).waitFor({ state: "attached", timeout: 20000 });
        out.push({ op, ok: true });
      } else if (op === "evaluate") {
        const value = await st.page.evaluate(String(s.script || ""));
        out.push({ op, ok: true, value });
      } else if (op === "cookies") {
        const cookies = s.url ? await st.context.cookies(String(s.url)) : await st.context.cookies();
        out.push({ op, ok: true, cookies });
      } else if (op === "screenshot") {
        const name = "nd-browser-reserve-" + kind + "-" + i + ".png";
        const opts = { type: "png", timeout: 15000 };
        if (s.full_page) opts.fullPage = true;
        if (s.selector) await st.page.locator(String(s.selector)).screenshot({ ...opts, path: name });
        else await st.page.screenshot({ ...opts, path: name });
        out.push({ op, ok: true, artifact: name });
      } else {
        throw new Error("unsupported_browser_step:" + op);
      }
    }
    return { ok: true, provider: kind, tool: "browser_sequence", steps: out, request_key: requestKey || null };
  } finally {
    await st.close();
  }
}

async function browserSmoke(kind) {
  return await browserSequence(kind, { steps: [
    { op: "goto", url: "https://example.com" },
    { op: "read_text", selector: "h1", max_chars: 500 },
    ...(kind === "cloudflare" ? [{ op: "screenshot" }] : []),
  ]});
}

async function apifyFetch(path, options = {}) {
  if (!secrets.apify) throw new Error("apify_not_configured");
  const headers = {
    Authorization: "Bearer " + secrets.apify,
    Accept: "application/json",
    ...(options.headers || {}),
  };
  const r = await fetch(path.startsWith("http") ? path : "https://api.apify.com" + path, { ...options, headers });
  const text = await r.text();
  let body; try { body = text ? JSON.parse(text) : null; } catch { body = text; }
  if (!r.ok) throw new Error("apify_http_" + r.status + ":" + clean(typeof body === "string" ? body : JSON.stringify(body)));
  return body;
}

function actorId(raw) {
  const s = String(raw || "");
  if (!/^[A-Za-z0-9_-]+(?:~[A-Za-z0-9_.-]+)?$/.test(s)) throw new Error("invalid_actor_id");
  return s;
}

async function apifyCall(name, a = {}) {
  if (name === "account_status") {
    const body = await apifyFetch("/v2/users/me");
    return { ok: true, provider: "apify", user_id_present: Boolean(body?.data?.id), plan: body?.data?.plan || null };
  }
  if (name === "web_fetch") {
    if (!secrets.apify) throw new Error("apify_not_configured");
    const body = await apifyFetch("https://web-fetch.apify.actor/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: ensureHttpUrl(a.url),
        formats: Array.isArray(a.formats) && a.formats.length ? a.formats : ["markdown"],
      }),
    });
    return { ok: true, provider: "apify", result: body };
  }
  if (name === "run_actor_sync") {
    const id = actorId(a.actor_id);
    const body = await apifyFetch("/v2/acts/" + encodeURIComponent(id) + "/run-sync-get-dataset-items?timeout=" +
      Math.min(300, Math.max(1, Number(a.timeout_secs || 120))), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(a.input || {}),
    });
    return { ok: true, provider: "apify", actor_id: id, items: body };
  }
  if (name === "run_actor_async") {
    if (!requestKey) throw new Error("request_key_required_for_actor_start");
    const id = actorId(a.actor_id);
    const body = await apifyFetch("/v2/acts/" + encodeURIComponent(id) + "/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(a.input || {}),
    });
    return { ok: true, provider: "apify", actor_id: id, run: body?.data || body, request_key: requestKey };
  }
  if (name === "get_run") {
    const id = String(a.run_id || "");
    if (!/^[A-Za-z0-9_-]+$/.test(id)) throw new Error("invalid_run_id");
    const body = await apifyFetch("/v2/actor-runs/" + encodeURIComponent(id));
    return { ok: true, provider: "apify", run: body?.data || body };
  }
  if (name === "get_dataset_items") {
    const id = String(a.dataset_id || "");
    if (!/^[A-Za-z0-9_-]+$/.test(id)) throw new Error("invalid_dataset_id");
    const limit = Math.min(100, Math.max(1, Number(a.limit || 20)));
    const body = await apifyFetch("/v2/datasets/" + encodeURIComponent(id) + "/items?clean=true&limit=" + limit);
    return { ok: true, provider: "apify", items: body };
  }
  if (name === "abort_run") {
    const id = String(a.run_id || "");
    if (!/^[A-Za-z0-9_-]+$/.test(id)) throw new Error("invalid_run_id");
    const body = await apifyFetch("/v2/actor-runs/" + encodeURIComponent(id) + "/abort", { method: "POST" });
    return { ok: true, provider: "apify", run: body?.data || body };
  }
  throw new Error("unknown_apify_tool:" + name);
}

async function main() {
  if (!["lightpanda", "cloudflare", "apify"].includes(provider)) throw new Error("unsupported_provider");
  if (tool === "__tools__") {
    if (provider === "apify") return {
      ok: true, provider, configured: Boolean(secrets.apify),
      tools: ["account_status","web_fetch","run_actor_sync","run_actor_async","get_run","get_dataset_items","abort_run"]
    };
    return {
      ok: true, provider,
      configured: provider === "lightpanda" ? Boolean(secrets.lightpanda) : Boolean(secrets.cloudflareAccount && secrets.cloudflareToken),
      tools: ["browser_sequence","__smoke__"],
      browser_steps: ["goto","get_url","read_text","html","click","fill","press","hover","select_option","set_checked","wait_for_selector","evaluate","cookies","screenshot"]
    };
  }
  if (tool === "__smoke__") {
    if (provider === "apify") {
      const status = await apifyCall("account_status", {});
      const fetched = await apifyCall("web_fetch", { url: "https://example.com", formats: ["markdown"] });
      const text = JSON.stringify(fetched);
      if (!/Example Domain/i.test(text)) throw new Error("apify_smoke_content_mismatch");
      return { ok: true, provider: "apify", account_verified: true, web_fetch_verified: true };
    }
    return await browserSmoke(provider);
  }
  if (provider === "apify") return await apifyCall(tool, args);
  if (tool === "browser_sequence") return await browserSequence(provider, args);
  throw new Error("unknown_tool");
}

try {
  save(await main(), true);
} catch (e) {
  save({ ok: false, provider, tool, error: clean(e?.message || e) }, false);
  process.exit(1);
}
