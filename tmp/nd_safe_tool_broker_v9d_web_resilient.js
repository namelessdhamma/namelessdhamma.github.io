console.log('ND_SAFE_TOOL_BROKER_V9D_WRAPPER_START');
const BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/5c5d5ced15d67ee1c0d52b53aec939f9fc82227d/tmp/nd_safe_tool_broker_v9c_web_resilient.js';
let src=await (await fetch(BASE)).text();
const old='r.status===429?1500:800';
if(!src.includes(old)) throw new Error('v9d retry marker missing');
src=src.replace(old,'r.status===429?12000:800');
src=src.replace('ND_SAFE_TOOL_BROKER_V9C_WEB_RESILIENT_START','ND_SAFE_TOOL_BROKER_V9D_WEB_RESILIENT_START');
await Bun.write('/tmp/nd-broker-v9d-inner.js',src);
await import('file:///tmp/nd-broker-v9d-inner.js');
