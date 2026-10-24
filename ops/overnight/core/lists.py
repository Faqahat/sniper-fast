#!/usr/bin/env python3
# Leak-free deployer lists: deployers (create signers) each case-study wallet ATTEMPTED (bought or failed) BEFORE a cutoff
# time, from (1) their ledgers' owner-RPC window (devs_*/att_* files, 10-20..10-22) and (2) the collector runs.
import sys, json, os, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
DC = "/home/moiz/sniper/ops/snipers/devcheck"
def build(cutoff_bt, L=None):
    L = L or rp.load_launches(); A = json.load(open("/home/moiz/sniper/ops/overnight/core/attempts.json"))
    lists = collections.defaultdict(collections.Counter); seen = collections.defaultdict(set)
    for w in ("9Sh2fd", "DGmspi"):
        for f in (f"devs_{w}.json", f"att_{w}.json"):
            p = os.path.join(DC, f)
            if not os.path.exists(p): continue
            for m, v in json.load(open(p)).items():
                if v.get("signer") and v.get("bt") and v["bt"] < cutoff_bt and m not in seen[w]:
                    lists[w][v["signer"]] += 1; seen[w].add(m)
    for m, v in A.items():
        c = L.get(m)
        if not c or not c.get("bt") or c["bt"] >= cutoff_bt: continue
        for w in v:
            if m not in seen[w]: lists[w][c["user"]] += 1; seen[w].add(m)
    return lists
if __name__ == "__main__":
    import datetime
    cut = datetime.datetime(2026, 10, 22, 17, 9, tzinfo=datetime.timezone.utc).timestamp()
    ls = build(cut)
    for w, c in ls.items():
        print(w, "deployers attempted before 10-22 17:09:", len(c), "| with >=2:", sum(1 for v in c.values() if v >= 2), "| >=3:", sum(1 for v in c.values() if v >= 3), "| attempts:", sum(c.values()))
    json.dump({w: dict(c) for w, c in ls.items()}, open("lists_cut1709.json", "w"))
