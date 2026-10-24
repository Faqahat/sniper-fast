#!/usr/bin/env python3
# Builds the S3 deployer list for the engine's --deployer-list gate (read-only research data -> a text file):
# deployers (create signers) with >= 2 attempts by 9Sh2fd / DGmspi and attempts / launches-we-saw >= 10%.
# Sources: the case wallets' ledger windows (devcheck files) + every collected launch and attempt (dry-run data).
import sys, os, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
L = rp.load_launches(); A = json.load(open(os.environ.get("ATTEMPTS_OUT", "/home/moiz/sniper/ops/overnight/dryrun/attempts_dry.json")))
DC = "/home/moiz/sniper/ops/snipers/devcheck"
att = collections.Counter(); nl = collections.Counter(); seen = set()
for w in ("9Sh2fd", "DGmspi"):
    for f in (f"devs_{w}.json", f"att_{w}.json"):
        p = os.path.join(DC, f)
        if os.path.exists(p):
            for m, v in json.load(open(p)).items():
                if v.get("signer") and m not in L and m not in seen: att[v["signer"]] += 1; seen.add(m)
for m, c in L.items():
    nl[c["user"]] += 1
    if "9Sh2fd" in A.get(m, {}) or "DGmspi" in A.get(m, {}): att[c["user"]] += 1
keep = sorted(d for d, a in att.items() if a >= 2 and (nl[d] == 0 or a / nl[d] >= 0.10))
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "deployer_list.txt")
open(out, "w").write("\n".join(keep) + "\n")
print(f"deployer_list.txt: {len(keep)} deployers")
