#!/usr/bin/env python3
import argparse,json,pathlib,copy

# Evidence-backed bridge pronunciation projection:
# run 37499385085 / commit 5d34204568fd3653f01b548ace339fa1b2da4a6f
# brl2 isolated/guide evidence: CER 0.0645 PASS
# brl4 later V60Z60 evidence: guide CER 0.133 PASS
PATCH={
  "brl2":{
    "который":[64,64,64],
    "общим":[64,64],
    "незабвенным":[64,64,65,64],
  },
  "brl4":{
    "былого":[64,65,64],
    "осталось":[64,65,64],
    "неизменным":[64,64,65,64],
  }
}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",required=True); ap.add_argument("--output",required=True)
    a=ap.parse_args()
    score=json.loads(pathlib.Path(a.input).read_text())
    changed=[]
    for ph in score["phrases"]:
        if ph["id"] not in PATCH: continue
        for w in ph["words"]:
            if w["text"] in PATCH[ph["id"]]:
                new=PATCH[ph["id"]][w["text"]]
                if len(new)!=len(w["pitches"]):
                    raise SystemExit(f"pitch cardinality mismatch {ph['id']} {w['text']}")
                old=list(w["pitches"]); w["pitches"]=new
                changed.append({"phrase":ph["id"],"word":w["text"],"from":old,"to":new})
    score.setdefault("d1r5",{})["accepted_bridge_projection"]={
      "evidence_run":37499385085,
      "evidence_commit":"5d34204568fd3653f01b548ace339fa1b2da4a6f",
      "brl2":"flattened intra-word melody; prior guide CER 0.0645 PASS",
      "brl4":"flattened intra-word melody; pair with proven V60Z60 /v/ + /z/ timing offsets",
    }
    pathlib.Path(a.output).write_text(json.dumps(score,ensure_ascii=False,indent=2)+"\n")
    print(json.dumps({"changed":changed},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
