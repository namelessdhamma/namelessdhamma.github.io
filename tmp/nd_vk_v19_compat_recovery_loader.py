print("ND_V19_ORIGINAL_LOADER_ACTIVE",flush=True)
import ast,builtins,urllib.request
V17="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/23b4b0e95652355f3e8a01473fe944e899c87ace/tmp/nd_vk_gateway_v17_omniroute_reserve.py"
V18="https://raw.githubusercontent.com/namelessdhamma/namelessdhamma.github.io/main/tmp/nd_vk_gateway_v18_adaptive_router.py"
v17=urllib.request.urlopen(V17,timeout=30).read().decode("utf-8")
v18=urllib.request.urlopen(V18,timeout=30).read().decode("utf-8")
patch=None
for n in ast.parse(v18).body:
    if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="v18_patch_code" for t in n.targets):
        patch=ast.literal_eval(n.value);break
if not patch: raise RuntimeError("v18_patch_literal_missing")
cap={}
rc=builtins.compile
re=builtins.exec
G={"__name__":"__main__"}
def cp(source,filename,mode,*a,**k):
    if filename=="nd_vk_gateway_v13_independent_web.py":
        cap["src"]=source.decode("utf-8") if isinstance(source,(bytes,bytearray)) else source
    return rc(source,filename,mode,*a,**k)
def ep(obj,gl=None,lo=None):
    if getattr(obj,"co_filename","")=="nd_vk_gateway_v13_independent_web.py":
        cap["blocked"]=True;return None
    return re(obj,G,G)
G["compile"]=cp;G["exec"]=ep
re(rc(v17,"nd_v17_capture_entry.py","exec"),G,G)
if not cap.get("blocked") or not cap.get("src"): raise RuntimeError("v17_final_source_capture_failed")
P={"src":cap["src"]}
re(rc(patch,"nd_v18_patch_only.py","exec"),P,P)
P["_adaptive_code"]=P["_adaptive_code"].replace("],48,0.0)", "],1024,0.0)",1)
rr=P.get("_new_rr","")
bad="synth='User request:\n'+text[:7000]+'\n\nFresh web material gathered independently of the model provider:\n'+evidence[:28000]+'\n\nAnswer from this material. Cite direct source URLs actually present. Distinguish publication dates from page text when uncertain. Do not invent sources or current facts.'"
good="synth='User request:\\n'+text[:7000]+'\\n\\nFresh web material gathered independently of the model provider:\\n'+evidence[:28000]+'\\n\\nAnswer from this material. Cite direct source URLs actually present. Distinguish publication dates from page text when uncertain. Do not invent sources or current facts.'"
if bad not in rr: raise RuntimeError("v18_new_rr_escape_marker_missing")
rr=rr.replace(bad,good,1)
final=P["_pre"]+P["_adaptive_code"]+rr+P["_rr_end"]+P["_post"]
if P["_groq_gate"] not in final: raise RuntimeError("v18_final_groq_gate_missing")
final=final.replace(P["_groq_gate"],P["_adaptive_gate"],1)
if P["_thread_marker"] not in final: raise RuntimeError("v18_final_thread_marker_missing")
final=final.replace(P["_thread_marker"],"threading.Thread(target=adaptive_startup_probe,daemon=True).start()\n"+P["_thread_marker"],1)
final=final.replace("ND_VK_GATEWAY_V15B_FATHER_MIN_PROFILE_START","ND_VK_GATEWAY_V18_ADAPTIVE_ROUTER_START",1)
if "adaptive_startup_probe" not in final: raise RuntimeError("v18_final_assembly_failed")
print("ND_V18_FIXED_ASSEMBLY_READY",flush=True)
re(rc(final,"nd_vk_gateway_v18_fixed_runtime.py","exec"),{"__name__":"__main__"})
