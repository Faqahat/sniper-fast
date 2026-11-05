#!/usr/bin/env python3
"""QUIET4 step 4 [MEASURED]: the RECENT whale-follower signal. Full QUIET dump books rebuilt by the engine's own builder
(target/release/quiet_book --full --until X --now X: same dump rule, same follower rule, same journal format) from the raw recordings
into /home/moiz/sniper-data/filters3/quiet4/book/b*.jsonl. All dumps merged by identity (s, i, j). For every kept live position
(T2 and re-arm; whale = trigger whale / re-arm dumper), from the whale's dumps that closed before the trigger slot (s + 2 < s0)
and t < t0:
  rb1h / rb3h / rb6h  = (count, mean followers) in the last 1 / 3 / 6 h
  rbl5 / rbl10        = (count, mean followers) of its last 5 / 10 dumps within 24 h
  rb24                = (count, mean) in 24 h (parity check vs the engine's quiet.wh_dumps / wh_fol)
Only when the book's sessions cover [t0 - W, t0] for that window (else None). Out: recent_book.pkl {position id: dict}."""
import sys, json, glob, pickle, bisect, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/quiet4")
import q4lib as L

dumps = {}; sess = []
for fn in sorted(glob.glob(f"{L.D}/book/b*.jsonl")):
    st = None
    for l in open(fn):
        d = json.loads(l)
        if d["k"] == "d": dumps[(d["s"], d["i"], d["j"])] = (d["t"], d["s"], d["w"], d["n"])
        elif d["k"] == "start": st = d["t"]
        elif d["k"] == "stop" and st is not None: sess.append((st, d["t"])); st = None
sess.sort(); merged = []
for a, b in sess:
    if merged and a <= merged[-1][1] + 120e9: merged[-1][1] = max(merged[-1][1], b)
    else: merged.append([a, b])
by = collections.defaultdict(list)
for t, s, w, n in dumps.values(): by[w].append((t, s, n))
for w in by: by[w].sort()
print("dumps", len(dumps), "sellers", len(by), "coverage", [(L.pkt(a), L.pkt(b)) for a, b in merged])


def covered(lo, hi): return any(a <= lo and hi <= b + 60e9 for a, b in merged)


X = pickle.load(open(f"{L.D}/feats.pkl", "rb")); P = X["P"]
out = {}; par = []
for p in P:
    w, t0, s0 = p["whale"], p["t0"], p["trig_slot"]
    if not w or not s0: continue
    v = [(t, n) for t, s, n in by.get(w, []) if s + 2 < s0 and t < t0]
    r = {}
    for key, hh in (("rb1h", 1), ("rb3h", 3), ("rb6h", 6), ("rb24", 24)):
        if not covered(t0 - hh * 3.6e12, t0): r[key] = None; continue
        x = [n for t, n in v if t >= t0 - hh * 3.6e12]
        r[key] = (len(x), sum(x) / len(x) if x else -1.0)
    if covered(t0 - 24 * 3.6e12, t0) or covered(t0 - 6 * 3.6e12, t0):
        x = [n for t, n in v if t >= t0 - 24 * 3.6e12]
        for key, k in (("rbl5", 5), ("rbl10", 10)):
            y = x[-k:]; r[key] = (len(y), sum(y) / len(y) if y else -1.0)
    else: r["rbl5"] = r["rbl10"] = None
    out[p["id"]] = r
    q = p["quiet"] or {}
    if r.get("rb24") and q.get("wh_dumps") is not None and q.get("rule_on") is not False: par.append((r["rb24"][0], q["wh_dumps"], r["rb24"][1], q.get("wh_fol")))
pickle.dump(out, open(f"{L.D}/recent_book.pkl", "wb"))
cov = collections.Counter((p["per"], (out.get(p["id"]) or {}).get("rb3h") is not None) for p in P)
print("rb3h coverage", sorted(cov.items()))
if par:
    ex = sum(1 for a, b, c, d in par if a == b); close = sum(1 for a, b, c, d in par if abs(a - b) <= max(1, 0.1 * b))
    print(f"parity vs engine (24 h whale dumps): {len(par)} positions, exact count {ex}, within 10% {close}")
