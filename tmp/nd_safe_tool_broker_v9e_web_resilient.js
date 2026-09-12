console.log('ND_SAFE_TOOL_BROKER_V9E_WRAPPER_START');
const BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/c82534fd087a79167879c8765ba2c07eee74573d/tmp/nd_safe_tool_broker_v9d_web_resilient.js';
let src=await (await fetch(BASE)).text();
const old='const payload={model:plan.model,messages:[{role:"user",content:plan.query}]};';
if(!src.includes(old)) throw new Error('v9e web payload marker missing');
src=src.replace(old,'const payload={model:plan.model,messages:[{role:"user",content:plan.query}],max_completion_tokens:1200};');
src=src.replace('ND_SAFE_TOOL_BROKER_V9D_WEB_RESILIENT_START','ND_SAFE_TOOL_BROKER_V9E_WEB_RESILIENT_START');
await Bun.write('/tmp/nd-broker-v9e-inner.js',src);
await import('file:///tmp/nd-broker-v9e-inner.js');
