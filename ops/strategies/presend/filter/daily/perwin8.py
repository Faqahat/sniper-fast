import sys, json
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filter")
import sim, rules
W = sim.load()
out = []
for w in W:
    r = sim.evaluate([w], arm=rules.quiet_arm, send=rules.c5_send)["ALL"]
    out.append(dict(run=w["run"], t=w["t"], spend=w["spend"], filled=bool(w["filled"]), before=r["before"], after=r["after"], kept=int(r.get("fills_kept", 0)), realized=(w.get("realized") or 0)/1e9 if w["filled"] else 0.0, rent=(w.get("rent_back") or 0)/1e9 if w["filled"] else 0.0, net=(w.get("net") or 0)/1e9 if w["filled"] else 0.0))
json.dump(out, open(sys.argv[1], "w"))
import collections
s = collections.defaultdict(lambda: [0.0, 0.0, 0])
for o in out: s[o["run"]][0] += o["before"]; s[o["run"]][1] += o["after"]; s[o["run"]][2] += 1
for k, v in sorted(s.items()): print(k, f"{v[0]:+.3f} -> {v[1]:+.3f}  windows {v[2]}")
print("t sample", out[0]["t"])
