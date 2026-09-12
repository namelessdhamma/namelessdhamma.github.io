console.log('ND_SAFE_TOOL_BROKER_V9C_WRAPPER_START');
const BASE='https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/1c01b3551cdce1997c46aa81dd2ae4c72a551b72/tmp/nd_safe_tool_broker_v9b_web_resilient.js';
let src=await (await fetch(BASE)).text();
const old=',citation_options:"enabled"';
if(!src.includes(old)) throw new Error('v9c citation marker missing');
src=src.replace(old,'');
src=src.replace('ND_SAFE_TOOL_BROKER_V9B_WEB_RESILIENT_START','ND_SAFE_TOOL_BROKER_V9C_WEB_RESILIENT_START');
await Bun.write('/tmp/nd-broker-v9c-inner.js',src);
await import('file:///tmp/nd-broker-v9c-inner.js');
