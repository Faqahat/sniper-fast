# FORWARD 2s-scalp score, REALISTIC: entry = real post-bundle price (from the create block) x landing slip, own impact on
# buy+sell, pump fee 1.25%/side, tx fees. Rules LOCKED 2026-10-18 15:46 before scoring: sell at +5% or at 2 s.
# Fresh = forward trades after #81 (rules were chosen looking only at the first 81).
import sys, re, json, statistics as st
src = open("/root/bsplit/real_his.py").read().split("for slip in (1.00, 1.04):")[0]
sys.argv = ["x", "fwd", "/root/bsplit/out_fwd.jsonl", "/root/sniper-fast/paths_blfwd.jsonl"]
exec(src)
CUT = 81
order = [m.group(1) for m in re.finditer(r"PAPER done mint=(\w+)", open("/root/sniper-fast/paper_blfwd.log").read())]
fresh = set(order[CUT:])
FR = [r for r in D if r["set"] == "fwd" and r["mint"] in fresh]
print(f"forward done {len(order)}, fresh (after #{CUT}) {len(fresh)}, scored {len(FR)} "
      f"(bundled {sum(bundled(r) for r in FR)}, no-bundle {sum(not bundled(r) for r in FR)})")
LEGS, T, SL = [(1.0, 1.05)], 2000, None
print(f"\n{'rule':26} {'landing spot':38} {'n':>4} {'avg':>7} {'median':>7} {'ex-top3':>8} {'win':>5}  total SOL @1 SOL/trade")
for name, f in [("A: bundled only", bundled), ("B: all launches", lambda r: True)]:
    for slip, prio, lab in [(1.00, 0.013, "his spot (first behind bundle), hi fee"), (1.06, 0.0003, "OUR spot today (~6% later)"),
                            (1.08, 0.0003, "~8% later")]:
        v = [run(r, slip, LEGS, T, SL, None, prio) for r in FR if f(r)]
        if not v:
            continue
        ex = sorted(v)[:-3] if len(v) > 15 else v
        print(f"{name:26} {lab:38} {len(v):4} {st.mean(v):+7.1%} {st.median(v):+7.1%} {st.mean(ex):+8.1%} {sum(x>0 for x in v)/len(v):5.0%}  {sum(v):+.2f}")
