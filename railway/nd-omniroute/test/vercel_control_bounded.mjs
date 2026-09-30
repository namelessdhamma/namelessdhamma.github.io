import fs from 'node:fs';
import assert from 'node:assert/strict';

const src=fs.readFileSync(new URL('../vercel_control.mjs',import.meta.url),'utf8');

assert.match(src,/const HTTP_TIMEOUT_MS=/);
assert.match(src,/async function boundedFetch\(/);
assert.match(src,/globalThis\.fetch\(/);
assert.equal((src.match(/await fetch\(/g)||[]).length,0,'raw awaited fetch must not remain');
assert.ok((src.match(/await boundedFetch\(/g)||[]).length>=10,'external provider I/O must be bounded');
assert.match(src,/runtime_profile:'BOUNDED_SYNC'/);
assert.match(src,/ambiguous_write:'READBACK_BEFORE_RETRY'/);
assert.match(src,/request_timeout_ms:HTTP_TIMEOUT_MS/);
assert.match(src,/Ambiguous writes require provider readback before retry/);

console.log('VERCEL_CONTROL_BOUNDED_IO=PASS');
