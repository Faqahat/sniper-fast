#!/usr/bin/env python3
"""SELLID step 10 (read-only): example lots with links. GMGN token page filtered to haqq; Solscan txs of his buy and sell (bots/hsigs.pkl)
and of the candidate trigger (the outside trade right before his sell; signature looked up in the raw recordings by slot+index).
Out: sellid/s10_examples.json, s10.txt"""
import pickle, json, glob, os, gzip, subprocess, time
import numpy as np
OUT = "/home/moiz/sniper-data/haqq_dissect/sellid"
HQ = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
pkt = lambda t: time.strftime("%m-%d %H:%M:%S", time.gmtime(int(t) + 18000))
Z = pickle.load(open(f"{OUT}/s1.pkl", "rb")); LOTS = Z["lots"]; SELLS = {(s["mint"], s["k"]): s for s in Z["sells"]}
ids = json.load(open("/home/moiz/sniper-data/dv8/tab/ids.json")); idm = {k: i for i, k in enumerate(ids)}
sigs = pickle.load(open("/home/moiz/sniper-data/haqq_dissect/bots/hsigs.pkl", "rb"))
FILES = []
for f in glob.glob("/home/moiz/sniper-data/collect/run_*/txs/txs_*.jsonl.gz"):
    try: FILES.append((int(os.path.basename(f)[4:-9]), f))
    except ValueError: pass
FILES.sort()
starts = np.array([a for a, _ in FILES])


def raw_sig(slot, idx, bt):
    j = int(np.searchsorted(starts, bt, side="right")) - 1
    for f in [FILES[x][1] for x in (j, j - 1, j + 1) if 0 <= x < len(FILES)]:
        r = subprocess.run(f"zcat {f} | grep -m1 -F '\"s\":{slot},\"i\":{idx},'", shell=True, capture_output=True, text=True)
        if r.stdout.strip():
            d = json.loads(r.stdout.strip().splitlines()[0]); return d["sig"], d.get("signers", [None])[0]
    return None, None


def detail(l, why):
    s = SELLS[(l["mint"], l["first_sell_k"])]
    mint = ids[l["mint"]]
    # nearest outside trade before the sell
    trig = None
    if len(s["w_us"]):
        j = int(np.argmin(s["w_dcc"]))
        tslot = s["slot"] - int(s["w_ds"][j]);
        # tx index of the trigger: same slot -> idx gap known; else look it up from the lot path
        k = int(s["w_k"][j]); pk = np.flatnonzero(l["p_k"] == k)
        tidx = int(l["p_ix"][pk[0]]) if len(pk) else (s["idx"] - int(s["w_di"][j]) if s["w_ds"][j] == 0 else None)
        sig, signer = raw_sig(tslot, tidx, s["bt"]) if tidx is not None else (None, None)
        trig = dict(wallet=ids[int(s["w_us"][j])], side="buy" if s["w_bu"][j] else "sell", sol=round(float(s["w_so"][j]), 3), ms_before_his_sell=round(float(s["w_dcc"][j])),
                    slot_gap=int(s["w_ds"][j]), idx_gap=int(s["w_di"][j]) if s["w_ds"][j] == 0 else None, tx=f"https://solscan.io/tx/{sig}" if sig else None)
    nb = [x for x in zip(s["w_bu"].tolist(), s["w_dcc"].tolist()) if x[0]]
    return dict(why=why, bot=l["code"], mint=mint, gmgn=f"https://gmgn.ai/sol/token/{mint}?maker={HQ}", time_pkt=pkt(l["bt"]),
                his_buy=f"https://solscan.io/tx/{sigs.get((l['slot'], l['idx']))}", his_sell=f"https://solscan.io/tx/{sigs.get((s['slot'], s['idx']))}",
                size_sol=round(l["cost"], 3), hold_ms=round(l["sell_dcc"]), pnl_msol=round(1000 * l["net"], 1),
                ms_since_last_outside_buy=round(min([d for b, d in nb], default=float("inf"))) if nb else None, trade_before_sell=trig)


def main():
    ex = []
    def pick(cond, why, n):
        v = [l for l in LOTS if l["first_sell_k"] is not None and (l["slot"], l["idx"]) in sigs and cond(l)]
        v.sort(key=lambda l: -l["bt"])
        for l in v[:n]: ex.append(detail(l, why))
    def trig_by(wpref, side):
        wid = [i for i, x in enumerate(ids) if x.startswith(wpref)][0]
        def f(l):
            s = SELLS[(l["mint"], l["first_sell_k"])]
            m = (s["w_us"] == wid) & (s["w_bu"] == side) & (s["w_dcc"] <= 212)
            return bool(m.any()) and float(s["w_dcc"][m].min()) == float(s["w_dcc"].min())
        return f
    pick(trig_by("7dMDTT4j", True), "248's top buy-lift wallet 7dMDTT4j bought right before his sell (the hypothesis' best case)", 2)
    pick(trig_by("2fg5QD1e", True), "4-wallet cluster (2fg5QD1e/suqh5sHt/7NAd2EpY/FxN3VZ4B) bought right before his sell", 1)
    pick(trig_by("HXHoJwF5", False), "co-seller HXHoJwF5 sold right before his sell", 1)
    def fast_pause(l):
        s = SELLS[(l["mint"], l["first_sell_k"])]
        b = s["w_bu"] & (s["w_dcc"] <= 500)
        return l["code"] == 247 and l["sell_dcc"] < 1000 and l["net"] > 0.02 and not b.any()
    pick(fast_pause, "247 fast winner (< 1 s): NO outside buy in the 500 ms before his sell (the typical case: sells into the pause)", 3)
    pick(lambda l: l["code"] == 247 and 4000 <= l["sell_dcc"] < 8000 and l["net"] < -0.01, "247 4-8 s loser", 1)
    json.dump(ex, open(f"{OUT}/s10_examples.json", "w"), indent=1)
    with open(f"{OUT}/s10.txt", "w") as f:
        for e in ex: f.write(json.dumps(e) + "\n")
    for e in ex: print(json.dumps(e))


if __name__ == "__main__":
    main()
