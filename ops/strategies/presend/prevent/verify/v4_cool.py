#!/usr/bin/env python3
"""VERIFY step 4: spot-check 3 of REGIME's cooldown rules with own code (scaled 0.696 series, verifier fixed costs).
Pause [t, t+K) blocks new window arms (window skipped with its fill + failed-try fees); events known at sell landing + 2 s;
skipped trades never trigger; a trigger inside a pause extends it."""
import pickle, collections, sys
OUT = "/home/moiz/sniper-data/prevent/verify"
T = pickle.load(open(f"{OUT}/tables.pkl", "rb"))
ORDER = ["F21", "F22", "F23", "F24", "F26", "F27", "F28", "A16", "A17", "A19", "A20", "A24", "A25", "A26", "A27", "A34", "A35", "A36", "A37", "A38"]
tw = {}
for x in T["trades"]: tw[(x["run"], x["w"])] = x
W = collections.defaultdict(list)
for w in T["wins"]: W[w["run"]].append(w)

def val(w):
    x = tw.get((w["run"], w["w"]))
    v = -w["wfee"]
    if x: v += x["s"] if x["kind"] == "t2" else x["unit"]
    return v, x

def run_rule(run, rule, K):
    ws = sorted(W[run], key=lambda w: w["t"]); pause_until = -1; known = []  # (t_known, x) of kept trades
    skipped = []; kept_seq = []
    import heapq
    pend = []
    hist = collections.deque(); streak = 0; cum = 0.0
    for w in ws:
        ta = w["t"]
        while pend and pend[0][0] <= ta:
            tk, _, v, x = heapq.heappop(pend)
            cum += v; hist.append((tk, cum))
            trig = False
            if rule == "C1":
                trig = x["pnl"] / x["spend"] < -0.072
            elif rule == "C4":
                streak = streak + 1 if x["pnl"] < 0 else 0
                if streak >= 4: trig = True; streak = 0
            elif rule == "C5":
                while hist and hist[0][0] < tk - 900: hist.popleft()
                base = None
                # rolling 15-min P&L = cum now - cum 15 min ago (the value just before the window)
                trig = False
            if trig:
                pause_until = max(pause_until, tk + K * 60)
        if rule == "C5":
            # 15-min rolling P&L of kept events (trades known + fees) ending now
            pass
        v, x = val(w)
        if ta < pause_until:
            skipped.append((v, x)); continue
        if x:
            heapq.heappush(pend, (x["t_sell"] + 2.0, id(x), v + w["wfee"], x))
            cum -= w["wfee"]
        else:
            cum += v
    return skipped

def run_c5(run, X, K):
    import heapq
    ws = sorted(W[run], key=lambda w: w["t"]); pause_until = -1; pend = []; ev = []; skipped = []
    for w in ws:
        ta = w["t"]
        while pend and pend[0][0] <= ta:
            tk, _, v, x = heapq.heappop(pend); ev.append((tk, v))
            p15 = sum(vv for tt, vv in ev if tt > tk - 900)
            if p15 < -X: pause_until = max(pause_until, tk + K * 60)
        v, x = val(w)
        if ta < pause_until: skipped.append((v, x)); continue
        ev.append((ta, -w["wfee"]))
        if x: heapq.heappush(pend, (x["t_sell"] + 2.0, id(x), v + w["wfee"], x))
    return skipped

for name, fn in (("C1 big loss -> pause 15m", lambda r: run_rule(r, "C1", 15)), ("C4 4 losses in a row -> pause 15m", lambda r: run_rule(r, "C4", 15)),
                 ("C5 15m P&L < -0.25 -> pause 15m", lambda r: run_c5(r, 0.25, 15))):
    per = {}
    for run in ORDER:
        sk = fn(run); per[run] = -sum(v for v, x in sk)
    pick = sum(v for r, v in per.items() if r not in ("A37", "A38"))
    h = sum(1 for r, v in per.items() if r not in ("A37", "A38") and v > 1e-9); u = sum(1 for r, v in per.items() if r not in ("A37", "A38") and v < -1e-9)
    print(f"{name:36s} PICK {pick:+.3f} ({h}/{u}) r37 {per['A37']:+.3f} r38 {per['A38']:+.3f}")
