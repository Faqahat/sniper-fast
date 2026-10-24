#!/usr/bin/env python3
# READ-ONLY, offline: what drives 9qz7cW's LATER-entry results (collector windows, SOL-quoted, filled first buys).
#  - result by its buy size, its own price impact, the flow of OTHER wallets after its buy (fast snipers vs the rest),
#    and who bought from its ladder (the counterparties of its sells: buys by others between its buy and its last sell)
#  - what it picks among launches that met the generic momentum trigger (later_strat L2) vs what it skipped
# -> later_dive.txt
import sys, os, json, collections, statistics as st
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__)); W = "9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw"
FS = set(json.load(open(os.path.join(HERE, "fast_snipers.json"))))
PL = json.load(open(os.path.join(HERE, "perlaunch_q9z.json"))); L = rp.load_launches()
LS = json.load(open(os.path.join(HERE, "later_strat.json")))["res"]
TB = {}
import gzip
for l in gzip.open("/home/moiz/sniper-data/collect/paper/table_dump.jsonl.gz", "rt"):
    r = json.loads(l); TB[r["mint"]] = r
later = {m: r for m, r in PL.items() if r["beh"] == "later" and r.get("buy_sig") and r["quote"] == "SOL" and not r["may"]}
jobs = collections.defaultdict(set)
for m in later: jobs[(L[m]["run"], rp.bucket(m))].add(m)
def work(job):
    run, b = job; tra = rp.read_bucket(run, b, jobs[job]); out = {}
    for m, tr in tra.items():
        p = later[m]; k = next((i for i, t in enumerate(tr) if t["sig"] == p["buy_sig"]), None)
        if k is None or not tr[k]["vtok"] or k == 0: continue
        t = tr[k]; s0 = t["s"]
        pre = tr[k - 1]["vsol"] / tr[k - 1]["vtok"]; post = t["vsol"] / t["vtok"]
        mine = [x for x in tr if x["user"] == W and not x["buy"] and x["s"] >= s0]
        last_s = mine[-1]["s"] if mine else s0 + 95
        oth = [x for x in tr if x["s"] >= s0 and x["s"] <= last_s and x["user"] != W and tr.index(x) > k] if False else [x for x in tr[k + 1:] if x["s"] <= last_s and x["user"] != W]
        b_fs = sum(x["sol"] for x in oth if x["buy"] and x["user"] in FS) / 1e9; b_ot = sum(x["sol"] for x in oth if x["buy"] and x["user"] not in FS) / 1e9
        s_ot = sum(x["sol"] for x in oth if not x["buy"]) / 1e9
        sold = sum(x["sol"] for x in mine) / 1e9
        w10 = [x for x in tr[k + 1:] if x["s"] <= s0 + 47 and x["user"] != W]
        out[m] = dict(size=t["sol"] / 1e9, impact=post / pre, sold=sold, res=p["sol_result"], buys_after_fs=b_fs, buys_after_other=b_ot, sells_after=s_ot,
                      flow10_after=sum((x["sol"] if x["buy"] else -x["sol"]) for x in w10) / 1e9, n_buyers_after=len({x["user"] for x in oth if x["buy"]}),
                      hold_slots=last_s - s0, run=run)
    return out
if __name__ == "__main__":
    R = {}
    with Pool(10) as pool:
        for o in pool.imap_unordered(work, sorted(jobs)): R.update(o)
    out = []
    def P(x): print(x, flush=True); out.append(x)
    v = list(R.values())
    P(f"later first buys analysed: {len(v)}; result {sum(x['res'] for x in v):+.2f} SOL")
    def grp(name, key, rows=v):
        g = collections.defaultdict(list)
        for x in rows: g[key(x)].append(x)
        P(f"\n== by {name}: n | result SOL | mean | win | its impact med | others' buys after it (SOL, med) | of which fast snipers (med)")
        for k_, xs in sorted(g.items(), key=lambda kv: str(kv[0])):
            P(f"   {str(k_):14} {len(xs):4d} {sum(x['res'] for x in xs):+8.2f} {st.mean(x['res'] for x in xs):+.3f} {sum(1 for x in xs if x['res'] > 0) / len(xs):4.0%}"
              f"  x{st.median(x['impact'] for x in xs):.3f}  {st.median(x['buys_after_other'] + x['buys_after_fs'] for x in xs):7.2f}  {st.median(x['buys_after_fs'] for x in xs):6.2f}")
    grp("its buy size (SOL)", lambda x: "<2" if x["size"] < 2 else "2-3" if x["size"] < 3 else "3-5" if x["size"] < 5 else "5-10" if x["size"] < 10 else "10+")
    grp("others' net flow 10 s after its buy", lambda x: "<0" if x["flow10_after"] < 0 else "0-3" if x["flow10_after"] < 3 else "3-10" if x["flow10_after"] < 10 else "10+")
    grp("distinct buyers after it (until its last sell)", lambda x: "<10" if x["n_buyers_after"] < 10 else "10-30" if x["n_buyers_after"] < 30 else "30+")
    tot_b = sum(x["buys_after_other"] + x["buys_after_fs"] for x in v); tot_fs = sum(x["buys_after_fs"] for x in v)
    P(f"\nbuys by others between its buy and its last sell: {tot_b:.1f} SOL, of which fast snipers {tot_fs:.1f} SOL ({tot_fs / max(1e-9, tot_b):.0%}); its sells {sum(x['sold'] for x in v):.1f} SOL")
    # its picks vs the generic momentum candidates it skipped (L2 300 ms decisions)
    cand = {m: x for m, x in LS.items() if "L2_300ms" in x["r"]}
    pick = [m for m in cand if cand[m]["its_later"]]; skip = [m for m in cand if not cand[m]["its_later"]]
    def f(m, k):
        try: return float(TB.get(m, {}).get(k))
        except (TypeError, ValueError): return None
    P(f"\n== generic momentum candidates (L2 trigger met): {len(cand)}; it attempted {len(pick)} ({len(pick) / max(1, len(cand)):.0%})")
    for k_, lab in (("dev_buy", "dev buy SOL"), ("glued_sol", "bundle SOL"), ("cr_prior_n", "deployer prior launches"), ("has_tw", "has twitter"), ("has_web", "has website"),
                    ("payer_is_creator", "payer is creator"), ("fslot_nb", "create-slot buys"), ("f5s_px", "price x at 5 s"), ("f15s_px", "price x at 15 s")):
        a = [f(m, k_) for m in pick if f(m, k_) is not None]; b_ = [f(m, k_) for m in skip if f(m, k_) is not None]
        if a and b_: P(f"   {lab:26} picked med {st.median(a):8.3f} mean {st.mean(a):8.3f} | skipped med {st.median(b_):8.3f} mean {st.mean(b_):8.3f}")
    for nm, ms in (("picked", pick), ("skipped", skip)):
        vv = [cand[m]["r"]["L2_300ms"]["base"]["ladder"] for m in ms if cand[m]["r"]["L2_300ms"].get("base")]
        ww = [cand[m]["r"]["L2_300ms"]["fs"]["ladder"] for m in ms if cand[m]["r"]["L2_300ms"].get("fs")]
        P(f"   our L2 ladder result on its {nm}: {sum(vv):+.2f} SOL n {len(vv)} (fast snipers removed {sum(ww):+.2f})")
    open(os.path.join(HERE, "later_dive.txt"), "w").write("\n".join(out) + "\n")
