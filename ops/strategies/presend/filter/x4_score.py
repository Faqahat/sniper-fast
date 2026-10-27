#!/usr/bin/env python3
"""EXPLORATION: a 'bot attention' points score (signals chosen on the chain-wide TUNING events, a3_chain.py: each one doubles the share of
fills nobody follows). Each point = one quiet signal at the trigger. Shown on chain tuning events (proxy) and on DEV live windows."""
import json
import numpy as np
import sim
B = "/home/moiz/sniper-data/presend_filter"
T_VAL0, T_VAL1 = 1792948200, 1793033220
E = [e for e in json.load(open(f"{B}/chain_events.json")) if not (T_VAL0 <= e["bt"] < T_VAL1)]
SIG = {
    "quiet_slot": lambda r: r.get("since_last", 0) >= 1,          # no trade earlier in the trigger's slot
    "no_coh_hold": lambda r: r.get("coh_hold", 0) == 0,           # no cohort bot holds the token
    "few_fbots": lambda r: r.get("fb_n", 0) < 2,                  # < 2 follower bots ever traded it
    "whale_unfollowed": lambda r: r.get("wh_dump_fol", -1) < 2.24, # the whale's earlier dumps drew < 2.24 buyers (or none known)
}


def score(r): return sum(1 for f in SIG.values() if f(r))


F = [e for e in E if e["fill"]]
print("chain tuning fill-like events by score:")
for s in range(0, len(SIG) + 1):
    X = [e for e in F if score(e) == s]
    A = [e for e in E if score(e) == s]
    if X: print(f"  score {s}: events {len(A)} fills {len(X)} proxy mean {np.mean([e['y_net'] for e in X]) * 1000:+.1f} mSOL dead {np.mean([e['y_nf'] == 0 for e in X]) * 100:.0f}%")
W = sim.load(("ams:r24", "ams:r25"))
print("DEV live windows by score:")
for s in range(0, len(SIG) + 1):
    X = [w for w in W if w["chain_ok"] and score(w) == s]
    Fx = [w for w in X if w["filled"]]
    if X: print(f"  score {s}: windows {len(X)} fills {len(Fx)} net {sum(w['net'] for w in Fx) / 1e9:+.3f} wins {sum(1 for w in Fx if w['net'] > 0)} notrade {sum(1 for w in Fx if w.get('y_nb') == 0)} fees {sum(w['fail_fee'] for w in X) / 1e9:.3f}")
for thr in (3, 4):
    r = sim.evaluate(W, arm=lambda w, thr=thr: not (w["chain_ok"] and score(w) >= thr))
    print(f"skip score >= {thr}:\n" + sim.fmt(r, ["ams:r24", "ams:r25"]))
