#!/usr/bin/env python3
# Step 1e: WHEN do the pre-placers start sending? Attempt streams (raw, failed included) per (wallet, mint), and for each fill:
# the burst of attempts that led to it (back from the fill while gaps <= GAP slots), its start vs the token's tape events
# (first >= 2% dump, biggest dump so far, the dumper's buy, token age), attempts per slot, failed attempts per fill.
# usage: python3 ps3c_streams.py <wallets.json>  -> presend/ps3c_bursts.jsonl + stdout summary per wallet
import sys, json, gzip, glob, collections, bisect
import numpy as np
import ps_common as C
GAP = 10          # slots: attempts closer than this belong to one burst
def load_streams(day, W):
    S = collections.defaultdict(list)
    for f in sorted(glob.glob(f"{C.OUT}/raw/{day}_*.jsonl.gz") + glob.glob(f"{C.OUT}/raw2/{day}_*.jsonl.gz")):
        for l in gzip.open(f, "rt"):
            r = json.loads(l)
            if r["w"] not in W or not r["mints"]: continue
            ix = " ".join(r["ixn"]); side = "B" if "Buy" in ix else ("S" if "Sell" in ix else "O")
            if r["tr"]: side = "B" if r["tr"][0][3] else "S"
            S[(r["w"], r["mints"][0])].append((r["s"], r["i"], side, r["err"], r["fee"] or 0, r["tips"]))
    return S

if __name__ == "__main__":
    W = set(json.load(open(sys.argv[1]))); out = []
    for day in ("R1", "R2", "R3", "R4"):
        d = C.load(day); mt = {x["m"]: t for t, x in enumerate(d["meta"])}
        ST = load_streams(day, W); nf = 0
        for (w, m), L in ST.items():
            t = mt.get(m)
            L.sort()
            # attempts = failed txs of any side "O"/"B" (conditional buys) ; fills = ok buys
            att = [x for x in L if x[2] in ("B", "O") and x[3] is not None]
            fills = [x for x in L if x[2] == "B" and x[3] is None]
            sells = [x for x in L if x[2] == "S" and x[3] is None]
            asl = [x[0] for x in att]
            for f in fills:
                sf = f[0]
                k = bisect.bisect_right(asl, sf) - 1          # attempts at or before the fill slot
                # walk back while gaps <= GAP
                k0 = k
                while k0 > 0 and asl[k0] - asl[k0 - 1] <= GAP: k0 -= 1
                n_b = (k - k0 + 1) if k >= 0 and sf - asl[k] <= GAP else 0
                b0 = asl[k0] if n_b else sf
                rec = dict(day=day, w=w, m=m, fill_s=sf, fill_i=f[1], burst_n=n_b, burst_start=b0, burst_slots=sf - b0,
                           burst_active_slots=len(set(asl[k0:k + 1])) if n_b else 0, att_total_mint=len(att), fills_mint=len(fills),
                           first_att_s=asl[0] if asl else None, sell_s=[x[0] for x in sells if x[0] >= sf][:1])
                if t is not None:
                    o = int(d["off"][t]); n = int(d["cnt"][t]); S0 = d["meta"][t]["S0"]
                    Sl = d["s"][o:o + n]; MV = d["move"][o:o + n]; B = d["buy"][o:o + n]; SOL = d["sol"][o:o + n]; V = d["vsol"][o:o + n]
                    pre = Sl < b0                                  # tape before the burst start
                    dm = (B == 0) & (MV <= -2.0)
                    rec.update(age_burst_s=(b0 - S0) * 0.4, age_fill_s=(sf - S0) * 0.4, n_tr_before=int(pre.sum()),
                               n_dumps2_before=int((dm & pre).sum()), first_dump2_s=(int(Sl[dm][0]) if dm.any() else None),
                               maxdrop_before=float(-MV[pre & (B == 0)].min()) if (pre & (B == 0)).any() else 0.0,
                               curve_burst=float(V[pre][-1] / 1e9) if pre.any() else None,
                               trades_last3=int(((Sl >= b0 - 3) & pre).sum()), buys_sol_last3=float(SOL[(Sl >= b0 - 3) & pre & (B == 1)].sum() / 1e9))
                    # the fill in the tape: the dump right before it
                    jf = np.flatnonzero((Sl == sf) & (B == 1))
                    rec["in_tape"] = bool(len(jf))
                out.append(rec); nf += 1
        print(f"{day}: streams {len(ST)}, fills {nf}", flush=True)
    with open(f"{C.OUT}/ps3c_bursts.jsonl", "w") as f:
        for r in out: f.write(json.dumps(r, default=float) + "\n")
    # summary
    by = collections.defaultdict(list)
    for r in out: by[r["w"]].append(r)
    q = lambda x, p: float(np.percentile(x, p)) if len(x) else float("nan")
    print(f"\n{'wallet':10s} {'fills':>5s} {'att/fill':>8s} {'burst_n p50':>11s} {'burst slots p25/50/75':>22s} {'act slots p50':>13s} {'age@burst s p25/50/75':>22s} {'dumps2 before p50':>17s} {'no dump before %':>16s}")
    for w, R in sorted(by.items(), key=lambda x: -len(x[1])):
        bn = [r["burst_n"] for r in R]; bs = [r["burst_slots"] for r in R]; ac = [r["burst_active_slots"] for r in R]
        ag = [r["age_burst_s"] for r in R if r.get("age_burst_s") is not None]; nd = [r["n_dumps2_before"] for r in R if r.get("n_dumps2_before") is not None]
        tot_att = sum(r["att_total_mint"] for r in {(r["m"]): r for r in R}.values())
        print(f"{w[:9]:10s} {len(R):5d} {tot_att / max(len(R), 1):8.1f} {q(bn, 50):11.0f} {q(bs, 25):7.0f}/{q(bs, 50):5.0f}/{q(bs, 75):5.0f}      {q(ac, 50):13.0f} "
              f"{q(ag, 25):7.0f}/{q(ag, 50):5.0f}/{q(ag, 75):5.0f}      {q(nd, 50):17.0f} {100 * np.mean([x == 0 for x in nd]) if nd else float('nan'):16.0f}")
