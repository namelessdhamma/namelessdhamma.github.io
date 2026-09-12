import fs from 'node:fs/promises';
import path from 'node:path';

const VENDOR_ROOT = process.env.ND_VK_VENDOR_ROOT || '/app/vendor';
const BROKER_PIN = 'fe8a0ff9d029b3026b76d43863f1cc5e0168ae21/tmp/nd_safe_tool_broker_v13_research_qualification.js';
const originalFetch = globalThis.fetch;

function resolveVendorUrl(url) {
  const raw = typeof url === 'string' ? url : String(url?.url || url || '');
  const prefix = 'ndvendor://namelessdhamma.github.io/';
  if (!raw.startsWith(prefix)) return null;
  const rel = raw.slice(prefix.length);
  if (!/^[0-9a-f]{40}\//.test(rel)) throw new Error(`invalid ndvendor URL: ${raw}`);
  const resolved = path.resolve(VENDOR_ROOT, rel);
  const root = path.resolve(VENDOR_ROOT) + path.sep;
  if (!resolved.startsWith(root)) throw new Error(`ndvendor path escape denied: ${raw}`);
  return resolved;
}

globalThis.fetch = async function ndVendorFetch(input, init) {
  const local = resolveVendorUrl(input);
  if (!local) return originalFetch(input, init);
  const body = await fs.readFile(local);
  return new Response(body, {status: 200, headers: {'content-type': 'text/plain; charset=utf-8'}});
};

const brokerPath = path.join(VENDOR_ROOT, BROKER_PIN);
const brokerSource = await fs.readFile(brokerPath, 'utf8');
const encoded = Buffer.from(brokerSource, 'utf8').toString('base64');
console.log('ND_VK_BROKER_LOCAL_VENDOR_BOOT', JSON.stringify({pin: BROKER_PIN}), true);
await import(`data:text/javascript;base64,${encoded}`);
