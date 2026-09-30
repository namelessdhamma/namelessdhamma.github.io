process.env.KAGGLE_API_TOKEN='test-token';
process.env.KAGGLE_USERNAME_SLUG='testuser';

const [{submit:reserveSubmit},{createLtxMcpHandler}]=await Promise.all([
  import('../../vercel/nd-kaggle-ltx-reserve/lib/ltx-core.js?cross-route'),
  import('../ltx_mcp_v2.mjs?cross-route')
]);

const ok=o=>new Response(JSON.stringify(o),{status:200,headers:{'content-type':'application/json'}});

function mockProvider(){
  globalThis.fetch=async (url,opts={})=>{
    const u=String(url),body=opts.body?JSON.parse(String(opts.body)):{};
    if(u.includes('/security.OAuthService/IntrospectToken'))return ok({active:true,username:'testuser'});
    if(u.includes('/kernels.KernelsApiService/ListKernels'))return ok({kernels:[]});
    if(u.includes('/kernels.KernelsApiService/GetAcceleratorQuotaStatistics'))return ok({gpuQuota:{timeUsed:'0s',timeReserved:'0s',totalTimeAllowed:'108000s'}});
    if(u.includes('/kernels.KernelsApiService/SaveKernel'))return ok({versionNumber:1});
    if(u.includes('/kernels.KernelsApiService/GetKernelSessionStatus'))return ok({status:1});
    throw new Error('unexpected '+u);
  };
}

async function primarySubmit(args){
  const handler=createLtxMcpHandler();
  const body=Buffer.from(JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/call',params:{name:'ltx_generate_keyframes',arguments:args}}));
  const req={method:'POST',async *[Symbol.asyncIterator](){yield body;}};
  let out=Buffer.alloc(0);
  const res={writeHead(){},end(data){if(data)out=Buffer.concat([out,Buffer.isBuffer(data)?data:Buffer.from(data)]);}};
  await handler(req,res);
  const envelope=JSON.parse(out.toString('utf8'));
  if(envelope.result?.isError)throw new Error(envelope.result.content?.[0]?.text||'primary error');
  return envelope.result.structuredContent;
}

const args={
  start_image_url:'https://example.org/start.jpg',
  end_image_url:'https://example.org/end.jpg',
  prompt:'same logical request across routes',
  negative_prompt:'none',
  duration_seconds:2,
  width:512,
  height:288,
  seed:42,
  idempotency_key:'cross-route-fixture'
};
const reserveCfg={token:'test-token',username:'testuser',inputToken:'',railwayBase:'https://example.invalid'};

mockProvider();
const reserve=await reserveSubmit(args,reserveCfg);
mockProvider();
const primary=await primarySubmit(args);

if(!reserve.effect_id||!primary.effect_id)throw new Error('missing effect identity');
if(reserve.effect_id!==primary.effect_id)throw new Error('cross-route effect mismatch '+JSON.stringify({reserve:reserve.effect_id,primary:primary.effect_id}));
if(reserve.request_id!==primary.request_id)throw new Error('cross-route request mismatch '+JSON.stringify({reserve:reserve.request_id,primary:primary.request_id}));
console.log('ND_LTX_CROSS_ROUTE_IDENTITY=PASS',reserve.request_id);
