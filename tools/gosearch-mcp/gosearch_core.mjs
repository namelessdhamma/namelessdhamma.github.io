const API_URL='https://api.gosearch.ai/goai/response';

export function normalizeGoSearch(data){
  const message=String(data?.completion?.message ?? data?.message ?? '');
  return {
    message,
    conversation_id:data?.conversationId ?? data?.conversation_id ?? null,
    authority:'candidate_discovery_only',
    authoritative_drive_refetch_required:true,
    provider:'gosearch',
    provider_response:data
  };
}

export async function goSearchResponse({query,apiToken,cgid,fetchImpl=fetch}){
  const q=String(query ?? '').trim();
  if(!q) throw new Error('query required');
  if(q.length>30000) throw new Error('query too large');
  if(!apiToken) throw new Error('GOSEARCH_API_TOKEN is not configured');
  const form=new URLSearchParams();
  form.set('prompt',q);
  form.set('stream','false');
  form.set('ephemeral','true');
  form.set('aiOnly','false');
  if(cgid!==undefined && cgid!==null && String(cgid).trim()) form.set('cgid',String(cgid).trim());
  const res=await fetchImpl(API_URL,{method:'POST',headers:{Authorization:`Bearer ${apiToken}`,'Content-Type':'application/x-www-form-urlencoded'},body:form.toString()});
  const text=await res.text();
  if(!res.ok){
    if(res.status===401) throw new Error('gosearch_auth_failed');
    if(res.status===429) throw new Error('gosearch_rate_limited');
    throw new Error(`gosearch_http_${res.status}`);
  }
  let data;
  try{data=JSON.parse(text);}catch{throw new Error('gosearch_invalid_json');}
  return normalizeGoSearch(data);
}
