#!/usr/bin/env python3
import importlib.util, json
from pathlib import Path
p=Path(__file__).resolve().parent/"nd_social_direct_protocol_v01.py"
spec=importlib.util.spec_from_file_location("nd_social_direct_protocol_v01",p)
m=importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(m)
r=m.structural_selftest()
print(json.dumps(r,ensure_ascii=False,sort_keys=True))
raise SystemExit(0 if r.get("ok") else 1)
