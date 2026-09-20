import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

test('website loads modular app and preserves red title token', async () => {
  const html = await readFile(new URL('../index.html', import.meta.url), 'utf8');
  assert.match(html, /<script type="module" src="\.\/app\.js"><\/script>/);
  assert.match(html, /--r:#a62722/);
  assert.match(html, /<div class="title">СИНЕЕ МОРЕ<\/div>/);
});


test('website exposes AI v1.0-rc1 and keeps all visible setting controls', async () => {
  const html = await readFile(new URL('../index.html', import.meta.url), 'utf8');
  assert.match(html, /AI[^<]*1\.0-rc1/);
  assert.match(html, /data-rule="C"/);
  assert.match(html, /data-rule="D"/);
  assert.match(html, /data-rule="CD"/);
  assert.match(html, /data-mode="solo"/);
  assert.match(html, /data-level="easy"/);
  assert.match(html, /data-level="medium"/);
  assert.match(html, /data-level="hard"/);
  assert.match(html, /data-style="mixed"/);
  assert.match(html, /data-style="architect"/);
  assert.match(html, /data-style="hunter"/);
  assert.match(html, /data-style="sentinel"/);
  assert.match(html, /data-style="trickster"/);
});

test('browser controller uses only the unified AI engine for computer moves', async () => {
  const app = await readFile(new URL('../app.js', import.meta.url), 'utf8');
  assert.match(app, /import\s*\{\s*chooseMove\s*\}\s*from\s*['"]\.\/ai\/engine\.js['"]/);
  assert.doesNotMatch(app, /function\s+aiPick\s*\(/);
  assert.doesNotMatch(app, /function\s+search\s*\(/);
  assert.doesNotMatch(app, /fastHeuristic/);
  assert.doesNotMatch(app, /centerFlex/);
});


test('browser controller renders the active persona through personaName()', async () => {
  const app = await readFile(new URL('../app.js', import.meta.url), 'utf8');
  assert.match(app, /personaName\(\)/);
  assert.doesNotMatch(app, /persona\(\)\.name/);
});
