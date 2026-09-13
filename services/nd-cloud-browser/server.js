import express from "express";
import { chromium } from "playwright";
import { mkdir, appendFile, readFile } from "node:fs/promises";
import { createHash, timingSafeEqual } from "node:crypto";
import path from "node:path";

const VERSION = "0.1.0";
const PORT = Number(process.env.PORT || 3000);
const TOKEN = process.env.ND_CLOUD_BROWSER_TOKEN || "";
const PROFILE_DIR = process.env.ND_CLOUD_BROWSER_PROFILE_DIR || "/data/profile";
const LEDGER_DIR = process.env.ND_CLOUD_BROWSER_LEDGER_DIR || "/data/ledger";
const LEDGER_FILE = path.join(LEDGER_DIR, "commands.jsonl");
const DEFAULT_ALLOWED = ["example.com", "www.iana.org", "httpbin.org", "www.selenium.dev"];
const ALLOWED_HOSTS = new Set(
  (process.env.ND_CLOUD_BROWSER_ALLOWED_HOSTS || DEFAULT_ALLOWED.join(","))
    .split(",")
    .map(v => v.trim().toLowerCase())
    .filter(Boolean)
);
const TEXT_LIMIT = Math.max(1000, Math.min(50000, Number(process.env.ND_CLOUD_BROWSER_TEXT_LIMIT || 12000)));

if (!TOKEN) {
  throw new Error("ND_CLOUD_BROWSER_TOKEN is required");
}

await mkdir(PROFILE_DIR, { recursive: true });
await mkdir(LEDGER_DIR, { recursive: true });

let context = null;
let page = null;

function tokenMatches(candidate) {
  const a = Buffer.from(candidate || "");
  const b = Buffer.from(TOKEN);
  return a.length === b.length && timingSafeEqual(a, b);
}

function requireAuth(req, res, next) {
  const auth = req.get("authorization") || "";
  const candidate = auth.startsWith("Bearer ") ? auth.slice(7) : "";
  if (!tokenMatches(candidate)) {
    return res.status(401).json({ error: "UNAUTHORIZED" });
  }
  next();
}

function provenance(req) {
  return {
    chat_session: req.get("x-nd-chat-session") || null,
    task_id: req.get("x-nd-task-id") || null,
    run_id: req.get("x-nd-run-id") || null,
    agent: req.get("x-nd-agent") || null,
    controller: req.get("x-nd-controller") || null
  };
}

function safeUrl(raw) {
  try {
    const u = new URL(raw);
    u.username = "";
    u.password = "";
    u.search = "";
    u.hash = "";
    return u.toString();
  } catch {
    return null;
  }
}

function validateUrl(raw) {
  let u;
  try {
    u = new URL(raw);
  } catch {
    const err = new Error("INVALID_URL");
    err.status = 400;
    throw err;
  }
  if (!["http:", "https:"].includes(u.protocol)) {
    const err = new Error("UNSUPPORTED_SCHEME");
    err.status = 400;
    throw err;
  }
  if (!ALLOWED_HOSTS.has(u.hostname.toLowerCase())) {
    const err = new Error("HOST_NOT_ALLOWED");
    err.status = 403;
    throw err;
  }
  return u.toString();
}

async function ledger(req, operation, result, extra = {}) {
  const record = {
    ts: new Date().toISOString(),
    service: "nd-cloud-browser",
    version: VERSION,
    operation,
    result,
    ...provenance(req),
    ...extra
  };
  await appendFile(LEDGER_FILE, JSON.stringify(record) + "\n", "utf8");
}

async function ensurePage() {
  if (!context) {
    context = await chromium.launchPersistentContext(PROFILE_DIR, {
      headless: true,
      viewport: { width: 1280, height: 900 },
      acceptDownloads: true,
      args: [
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-background-networking"
      ]
    });
    context.on("close", () => {
      context = null;
      page = null;
    });
  }
  if (!page || page.isClosed()) {
    page = context.pages()[0] || await context.newPage();
  }
  return page;
}

async function closeContext() {
  if (context) {
    await context.close();
    context = null;
    page = null;
  }
}

const app = express();
app.disable("x-powered-by");
app.use(express.json({ limit: "256kb" }));

app.get("/health", (_req, res) => {
  res.json({ ok: true, service: "nd-cloud-browser", version: VERSION });
});

app.use("/v1", requireAuth);

app.get("/v1/status", async (req, res, next) => {
  try {
    const pages = context
      ? context.pages().filter(p => !p.isClosed()).map(p => safeUrl(p.url())).filter(Boolean)
      : [];
    await ledger(req, "status", "ok", { browser_started: Boolean(context), page_count: pages.length });
    res.json({
      ok: true,
      version: VERSION,
      browser_started: Boolean(context),
      persistent_profile: true,
      allowed_hosts: [...ALLOWED_HOSTS],
      page_count: pages.length,
      pages
    });
  } catch (e) {
    next(e);
  }
});

app.post("/v1/open", async (req, res, next) => {
  try {
    const target = validateUrl(req.body?.url);
    const p = await ensurePage();
    await p.goto(target, { waitUntil: "domcontentloaded", timeout: 45000 });
    const out = { ok: true, title: await p.title(), url: safeUrl(p.url()) };
    await ledger(req, "open", "ok", { url: out.url });
    res.json(out);
  } catch (e) {
    next(e);
  }
});

app.get("/v1/observe", async (req, res, next) => {
  try {
    const p = await ensurePage();
    const bodyText = await p.locator("body").innerText({ timeout: 15000 }).catch(() => "");
    const out = {
      ok: true,
      title: await p.title(),
      url: safeUrl(p.url()),
      text: bodyText.slice(0, TEXT_LIMIT)
    };
    await ledger(req, "observe", "ok", { url: out.url, text_chars: out.text.length });
    res.json(out);
  } catch (e) {
    next(e);
  }
});

app.post("/v1/click-text", async (req, res, next) => {
  try {
    const text = String(req.body?.text || "");
    if (!text || text.length > 500) {
      return res.status(400).json({ error: "INVALID_TEXT_TARGET" });
    }
    const exact = req.body?.exact !== false;
    const p = await ensurePage();
    await p.getByText(text, { exact }).first().click({ timeout: 15000 });
    const targetHash = createHash("sha256").update(text).digest("hex").slice(0, 16);
    const out = { ok: true, title: await p.title(), url: safeUrl(p.url()) };
    await ledger(req, "click_text", "ok", { target_hash: targetHash, url: out.url });
    res.json(out);
  } catch (e) {
    next(e);
  }
});

app.post("/v1/type", async (req, res, next) => {
  try {
    const selector = String(req.body?.selector || "");
    const text = String(req.body?.text ?? "");
    if (!selector || selector.length > 500 || text.length > 20000) {
      return res.status(400).json({ error: "INVALID_TYPE_REQUEST" });
    }
    const p = await ensurePage();
    await p.locator(selector).first().fill(text, { timeout: 15000 });
    const selectorHash = createHash("sha256").update(selector).digest("hex").slice(0, 16);
    await ledger(req, "type", "ok", { selector_hash: selectorHash, chars: text.length });
    res.json({ ok: true });
  } catch (e) {
    next(e);
  }
});

app.post("/v1/back", async (req, res, next) => {
  try {
    const p = await ensurePage();
    await p.goBack({ waitUntil: "domcontentloaded", timeout: 30000 }).catch(() => null);
    const out = { ok: true, title: await p.title(), url: safeUrl(p.url()) };
    await ledger(req, "back", "ok", { url: out.url });
    res.json(out);
  } catch (e) {
    next(e);
  }
});

app.get("/v1/screenshot", async (req, res, next) => {
  try {
    const p = await ensurePage();
    const png = await p.screenshot({ type: "png", fullPage: false });
    await ledger(req, "screenshot", "ok", { bytes: png.length });
    res.type("png").send(png);
  } catch (e) {
    next(e);
  }
});

app.post("/v1/close", async (req, res, next) => {
  try {
    await closeContext();
    await ledger(req, "close", "ok");
    res.json({ ok: true, profile_preserved: true });
  } catch (e) {
    next(e);
  }
});

app.get("/v1/ledger", async (req, res, next) => {
  try {
    const limit = Math.max(1, Math.min(200, Number(req.query.limit || 50)));
    const raw = await readFile(LEDGER_FILE, "utf8").catch(() => "");
    const rows = raw.trim() ? raw.trim().split("\n").slice(-limit).map(line => JSON.parse(line)) : [];
    res.json({ ok: true, records: rows });
  } catch (e) {
    next(e);
  }
});

app.use(async (err, req, res, _next) => {
  const status = Number(err.status || 500);
  const code = status >= 500 ? "BROWSER_OPERATION_FAILED" : String(err.message || "REQUEST_FAILED");
  await ledger(req, req.path || "unknown", "error", { error_code: code }).catch(() => {});
  res.status(status).json({ error: code });
});

const server = app.listen(PORT, "0.0.0.0", () => {
  console.log(JSON.stringify({ event: "started", service: "nd-cloud-browser", version: VERSION, port: PORT }));
});

async function shutdown(signal) {
  console.log(JSON.stringify({ event: "shutdown", signal }));
  await closeContext().catch(() => {});
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(1), 10000).unref();
}

process.on("SIGTERM", () => shutdown("SIGTERM"));
process.on("SIGINT", () => shutdown("SIGINT"));
