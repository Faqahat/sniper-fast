#!/usr/bin/env python3
"""verify2 / a10: hand check of individual fills against the RAW chunk lines (re-read straight from the .jsonl.gz, independent of
x1's extraction). Prints the create, glued bundle, the engine timeline, our placement, the tape through our 8 s sell with the
price multiple vs our entry, and the trades right after the sell. usage: python3 -I a10_handcheck.py <mint prefix> [L=75]"""
import sys, os, json, gzip, base64, glob, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v2core as V
pref = sys.argv[1]; Lm = int(sys.argv[2]) if len(sys.argv) > 2 else 75
P = V.load_picks(); m = next(x for x in P if x.startswith(pref)); L = V.load_launches([m]); D, O = V.load_scores([m]); X = V.load_x1()
SLIP, _ = V.load_slip(); ENG = json.load(open(os.path.join(V.WORK, "a6_engine.json")))
slots = {int(k): v for k, v in json.load(gzip.open(os.path.join(V.WORK, "x1_slots.json.gz"), "rt")).items()}
lo, hi = min(slots), max(slots); EMPTY = {s for s in range(lo, hi + 1) if slots.get(s, 0) == 0}
c = L[m]; M = V.Mint(m, c, X[m], repair=True, empty_slots=EMPTY)
outs = V.parse_outs(O[m]["outs"]); seen, miss, how = V.match_anchors(M, outs); ab = V.absorbed_units(M, ENG.get(m), seen)
ins = V.place2(M, seen, Lm, "opt", ab); o = V.replay(M, ins, slip=SLIP)
print(f"== {m}  {c.get('name')}  create slot {c['slot']} idx {c['idx']}  creator {c.get('creator')}")
print(f"   engine decide: at_ms {D[m]['at_ms']} glued_n {D[m]['features']['glued_n']} glued_sol {D[m]['features']['glued_sol']} dev_buy {D[m]['features']['dev_buy']:.3f} | absorbed extra {len(ab)}")
print(f"   engine outs (first 10): {outs[:10]}")
print(f"   chain glued units: {[M.units[u]['i'] for u in M.glued_units]}  post-bundle vsol {M.post_bundle[0] / 1e9:.4f}")
print(f"   our buy at {Lm} ms goes after unit {ins} = slot +{M.units[ins]['s'] - M.S} idx {M.units[ins]['i']} sig {M.units[ins]['sig']}")
print(f"   result: fill {o['fill']} ratio {o.get('ratio', 0):.4f} pnl {o.get('pnl', 0):+.4f} mult {o.get('mult', 0):.3f} sell before slot {o.get('sslot', 0) - M.S} (+{(o.get('sslot', 0) - o.get('bslot', 0)) * 0.212:.2f} s after our buy slot)")
# raw re-read of the chunk lines for this mint (independent of x1): decode TradeEvents directly
TE = bytes([189, 219, 127, 211, 78, 230, 97, 238]); A = V.__dict__.get("A")
files = sorted({r["file"] for r in X[m] if r["s"] - M.S <= 60})
raw = []
for f in files:
    for line in gzip.open(os.path.join("/home/moiz/sniper-data/collect/run_20261022_1543/txs", f), "rt"):
        if m not in line: continue
        r = json.loads(line)
        if r["s"] - M.S > 60 or r.get("err"): continue
        for e in r.get("ev") or []:
            try: b = base64.b64decode(e + "=" * (-len(e) % 4))
            except Exception: continue
            if b[:8] != TE or len(b) < 113: continue
            sol, tok = struct.unpack_from("<QQ", b, 40); vsol, vtok = struct.unpack_from("<QQ", b, 97)
            raw.append((r["s"], r["i"], r["sig"], b[56], sol, tok, vsol, vtok, (r.get("signers") or ["?"])[0]))
raw.sort(key=lambda x: (x[0], x[1]))
p_in = None
# entry price = our average price (X/q_me) from the replay: recompute
V0, T0 = None, None
for t in M.trades:
    if t["u"] <= ins: V0, T0 = t["vsol"], t["vtok"]
fr = 0.0125; Xs = int(0.5e9 / (1 + fr)); q = T0 * Xs // (V0 + Xs); q_me = int(q * 0.985); p_in = Xs / q_me
print(f"   entry: state before our buy vsol {V0 / 1e9:.4f}; our avg price {p_in:.3e} lamports/raw token ({p_in / (V0 / T0):.3f}x the pre-buy spot)")
print("   raw tape (slot+, idx, side, SOL, vsol after, spot/our-entry WITHOUT our buy, signer):")
ins_key = (M.units[ins]["s"], M.units[ins]["i"]); sell_slot = o.get("sslot")
for s, i, sig, b, sol, tok, vsol, vtok, who in raw:
    if s > (sell_slot or 0) + int(os.environ.get("AFTER", "4")): break
    tag = ""
    if (s, i) == ins_key: tag = "  <-- we land right after this tx"
    if sell_slot and s >= sell_slot and not getattr(sys, "_sold", False): tag += "  <== our 8 s sell lands before this trade"; sys._sold = True
    mult = (vsol / vtok) / p_in
    print(f"     +{s - M.S:3d} {i:4d} {'B' if b == 1 else 'S'} {sol / 1e9:8.4f} vsol {vsol / 1e9:8.3f} x{mult:5.2f} {who[:8]} {sig[:10]}{tag}")
