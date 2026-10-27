#!/usr/bin/env python3
"""VM1 independent check, step 4: our live fires joined with the CHAIN (raw recording), read-only.
For every fire in FRA dip_r1..r16 and AMS dip_ams_r9..r17:
  dump position (slot, idx) from my decoded trades (by signature), our buy tx (any fan-out variant) and its chain
  position + result, our sell tx(s), chain-measured SOL P&L of our wallet (all fees, tips, curve SOL), the log's
  REALIZED number, the engine's own dump record (M2 score / IMIT1 pass) and the run's settings.
Writes /home/moiz/sniper-data/vm1/live_fires.json"""
import json, glob, os, re, hashlib, collections
import numpy as np
import core

RUNS = "/home/moiz/sniper-data/runs"
W = {"fra": "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "ams": "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}

def sigh(sig):
    return int.from_bytes(hashlib.blake2b(sig.encode(), digest_size=8).digest(), "little")

def run_files():
    out = []
    for reg, pat in (("fra", "fra/runs/dip_r*.jsonl"), ("ams", "ams/runs/dip_ams_r*.jsonl")):
        for fn in glob.glob(os.path.join(RUNS, pat)):
            n = int(re.search(r"_r(\d+)\.jsonl", fn).group(1)); out.append((reg, n, fn))
    return sorted(out)

def main():
    D = core.Data()
    TA = np.load(os.path.join(core.D, "trades.npy"))              # all decoded trades (any curve) for dump lookup
    hix = {int(h): q for q, h in enumerate(TA["sigh"])} if False else None
    order = np.argsort(TA["sigh"]); hs = TA["sigh"][order]
    def find_trade(sig):
        h = np.uint64(sigh(sig)); q = np.searchsorted(hs, h)
        if q < len(hs) and hs[q] == h: return int(order[q])
        return None
    chain = collections.defaultdict(list); bysig = {}
    for line in open(os.path.join(core.D, "ours.jsonl")):
        r = json.loads(line); bysig[r["sig"]] = r
        for w in r["signers"]:
            for reg, ww in W.items():
                if w == ww:
                    for m in r.get("mints") or []: chain[(reg, m)].append(r)
    for v in chain.values(): v.sort(key=lambda r: (r["s"], r["i"]))
    fires = []
    for reg, n, fn in run_files():
        recs = []
        for line in open(fn):
            try: recs.append(json.loads(line))
            except Exception: pass
        start = next((r for r in recs if r.get("ev") == "run_start"), {})
        dumps = {r["sig"]: r for r in recs if r.get("ev") == "dump" and "sig" in r}
        logfn = fn[:-6] + ".log"; realized = []
        if os.path.exists(logfn):
            for l in open(logfn, errors="replace"):
                m = re.search(r"REALIZED mint=(\S+) pnl=([+-][0-9.]+) SOL", l)
                if m: realized.append((m.group(1), float(m.group(2))))
        rz = collections.defaultdict(list)
        for m, p in realized: rz[m].append(p)
        fl = [r for r in recs if r.get("ev") == "fire"]
        for q, f in enumerate(fl):
            mint = f["mint"]; cand = {f.get("buy_sig")}
            nz = f.get("nonce") or {}
            for p in nz.get("per_path") or []: cand.add(p.get("sig"))
            for p in nz.get("variants") or []: cand.add(p.get("sig"))
            cand.discard(None)
            txs = chain.get((reg, mint), [])
            buys = [t for t in txs if t["sig"] in cand]
            rec = {"region": reg, "run": n, "mint": mint, "dump_sig": f.get("dump_sig"), "fire_slot": f.get("slot"), "spend": f.get("spend"),
                   "dev": f.get("dev"), "leader": f.get("leader"), "client": f.get("client"), "route": f.get("route"), "t_fire": f.get("t_fire"),
                   "hold_slots": start.get("hold_slots"), "guard": start.get("guard"), "model": start.get("model"),
                   "m2_mode": (start.get("m2") or {}).get("mode"), "nonce": bool(nz), "n_cand": len(cand)}
            dt = find_trade(f["dump_sig"]) if f.get("dump_sig") else None
            if dt is not None:
                rec.update(dump_slot=int(TA["slot"][dt]), dump_idx=int(TA["idx"][dt]), dump_j=int(TA["j"][dt]), dump_sol=int(TA["sol"][dt]),
                           dump_vsol=int(TA["vsol"][dt]), dump_vtok=int(TA["vtok"][dt]), dump_buy=int(TA["buy"][dt]))
            dr = dumps.get(f.get("dump_sig"))
            if dr:
                rec.update(eng_m2=dr.get("m2"), eng_m2_pick=dr.get("m2_pick"), eng_imit_pass=dr.get("imit_pass"), eng_pass=dr.get("pass"),
                           eng_score=dr.get("score"), eng_launch_ok=dr.get("launch_ok"))
            if buys:
                b = buys[0]
                rec.update(buy_sig=b["sig"], buy_slot=b["s"], buy_idx=b["i"], buy_ok=b["err"] is None, buy_err=str(b["err"])[:60] if b["err"] else None,
                           buy_fee=b.get("fee"), buy_tips=sum(x[1] for x in b.get("tips") or []), n_landed=len(buys),
                           buy_sd=sum(x[1] for x in b.get("sd") or [] if x[0] == W[reg]))
                # sells: our Sell txs on this mint after the buy, before the next fire on the same mint
                nxt = next((g for g in fl[q + 1:] if g["mint"] == mint), None)
                lim = (nxt["slot"] if nxt else 10**12)
                sells = [t for t in txs if (t["s"], t["i"]) > (b["s"], b["i"]) and t["s"] < lim + 1 and any("Sell" in x for x in (t.get("ixn") or []))]
                if b["err"] is not None: sells = []          # a reverted buy holds nothing (a later sell belongs to another position)
                okc = [t for t in sells if t["err"] is None]
                rec["sell_txs"] = [{"sig": t["sig"], "slot": t["s"], "idx": t["i"], "ok": t["err"] is None, "fee": t.get("fee"),
                                    "tips": sum(x[1] for x in t.get("tips") or []), "sd": sum(x[1] for x in t.get("sd") or [] if x[0] == W[reg])} for t in sells]
                rec["chain_pnl"] = (rec["buy_sd"] + sum(s["sd"] for s in rec["sell_txs"])) / 1e9
                if b["err"] is None:
                    tb = [x for x in (b.get("tb") or []) if x[0] == mint and x[1] == W[reg]]
                    rec["tokens"] = (tb[0][3] - tb[0][2]) if tb else None
            if rz.get(mint):
                rec["realized_log"] = rz[mint].pop(0) if (buys and buys[0]["err"] is None) else None
            fires.append(rec)
    json.dump(fires, open(os.path.join(core.D, "live_fires.json"), "w"))
    c = collections.Counter((f["region"], "landed" if f.get("buy_sig") else "no_tx", f.get("buy_ok")) for f in fires)
    print(len(fires), c)
    print("dump found", sum(1 for f in fires if "dump_slot" in f), "engine dump rec", sum(1 for f in fires if "eng_m2" in f or "eng_pass" in f))

if __name__ == "__main__":
    main()
