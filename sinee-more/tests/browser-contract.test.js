import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('website loads modular app and preserves red title token', async () => {
  const html = await readFile(new URL('../index.html', import.meta.url), 'utf8');
  assert.match(html, /<script type="module" src="\.\/app\.js"><\/script>/);
  assert.match(html, /--r:#a62722/);
  assert.match(html, /<div class="title">СИНЕЕ МОРЕ<\/div>/);
});
