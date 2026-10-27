#!/usr/bin/env python3
"""DV8 step 1a (read-only): every live run record (AMS r9-r33, FRA r1-r26) -> one table per regular fire and per pre-send attempt,
joined with the tape (dv8/tab/ours.jsonl = our wallets' landed txs, fills AND failed).
Regular fire row: run, srv, t, mint, dump (slot, idx, sig), min_out, spend, leader/client at the dump slot, all copy sigs,
  first landed copy (slot, idx, err), outcome: fill / fail (landed with an error, guard = custom 6042) / none (no copy on chain),
  buy cost (fee + tips of every landed copy), realized P&L (our wallet SOL change over all our txs on the mint from the dump slot
  to +60 slots, excluding pre-send sigs), held to the run's exit (hold_slots).
Pre-send attempt row: run, t, mint, send slot, leader (8-char prefix -> full via schedule), client, path, landed (slot, idx, res).
Out: dv8/live_fires.pkl, dv8/live_presend.pkl"""
import json, pickle, collections, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
from runs import run_files
import dv8lib as L


def tsec(t): return t / 1e9 if t and t > 1e15 else t


def main():
    ours = {}; by_mint = collections.defaultdict(list)
    for l in open(f"{L.TAB}/ours.jsonl"):
        d = json.loads(l)
        if d["signers"][0] not in L.WAL.values(): continue
        sd = d["sd"]; sd = json.loads(sd.replace("'", '"')) if isinstance(sd, str) else sd
        tips = d.get("tips") or []
        r = dict(s=d["s"], i=d["i"], err=d["err"], fee=d["fee"], tips=sum(v for a, v in tips), sd=sum(v for a, v in sd if a == d["signers"][0]),
                 w=d["signers"][0], mint=(d["mints"] or [None])[0], sig=d["sig"], buy=any("Buy" in x for x in d.get("ixn") or []),
                 sell=any("Sell" in x for x in d.get("ixn") or []))
        ours[d["sig"]] = r
        if r["mint"]: by_mint[(r["w"], r["mint"])].append(r)
    print("our landed txs on tape:", len(ours), flush=True)
    fires = []; pres = []
    for run, f in run_files().items():
        srv = run[:3]; wal = L.WAL[srv]
        cfg = {}; dumps = {}; picks = {}; F = []; land = {}; fail = {}; psig = set(); patt = {}; pland = {}
        for l in open(f):
            try: d = json.loads(l)
            except Exception: continue
            e = d.get("ev"); t = tsec(d.get("t"))
            if e == "run_start": cfg = dict(spend=d.get("spend"), guard=d.get("guard"), hold=d.get("hold_slots"))
            elif e == "dump": dumps[d["sig"]] = d
            elif e == "pick": picks[d["sig"]] = d
            elif e == "fire":
                sigs = [d["buy_sig"]] + [p["sig"] for p in (d.get("nonce") or {}).get("per_path", [])] + [v["sig"] for v in d.get("variants", [])]
                F.append(dict(d, t=t, sigs=list(dict.fromkeys(sigs))))
            elif e == "buy_land": land[d["sig"]] = d
            elif e == "buy_failed": fail[d["sig"]] = d
            elif e == "presend_attempt":
                patt[d["sig"]] = dict(run=run, srv=srv, t=t, mint=d["mint"], send_slot=d.get("slot"), leader8=d.get("leader"), client=d.get("client"),
                                      path=d.get("path"), tip=d.get("tip"), spend=d.get("spend"), min_out=d.get("min_out"), pos=d.get("pos"), dry=d.get("dry"))
            elif e == "presend_attempt_land":
                pland[d["sig"]] = dict(slot=d.get("slot"), idx=d.get("idx"), res=d.get("res"), err=d.get("err"), ms_send_to_rx=d.get("ms_send_to_rx"),
                                       send_slot=d.get("send_slot"), ms_after_d=d.get("ms_after_d_a"), dslot=(d.get("d") or {}).get("slot"),
                                       didx=(d.get("d") or {}).get("idx"), n_between=d.get("n_between"), client=d.get("client"), path=d.get("path"))
            elif e in ("presend_live_fill",): psig.add(d["sig"])
            elif e == "presend_live_close":
                for b in d.get("buys") or []: psig.add(b["sig"])
                for s in d.get("sell_sigs") or []: psig.add(s[0])
            elif e == "presend_live_ata_close" and d.get("sig"): psig.add(d["sig"])
        psig |= set(patt) | set(pland)
        for sg, a in patt.items():
            a.update(pland.get(sg) or {}); a["landed"] = sg in pland
            o = ours.get(sg)
            a["tape"] = (o["s"], o["i"], o["err"] is None) if o else None
            pres.append(a)
        for d in F:
            dmp = dumps.get(d.get("dump_sig")) or {}; pk = picks.get(d.get("dump_sig")) or {}
            ds, di = dmp.get("slot") or pk.get("slot"), dmp.get("idx") if dmp.get("idx") is not None else pk.get("idx")
            landed = sorted([ours[s] for s in d["sigs"] if s in ours], key=lambda r: (r["s"], r["i"]))
            first = landed[0] if landed else None
            fill = next((r for r in landed if r["err"] is None), None)
            out = "fill" if fill else ("fail" if landed else ("eng_fill" if any(s in land for s in d["sigs"]) else ("eng_fail" if any(s in fail for s in d["sigs"]) else "none")))
            buy_cost = sum(r["fee"] + r["tips"] for r in landed) / 1e9
            # realized: all our txs on the mint (this wallet) from the dump slot to +60 slots, not pre-send
            tx = [r for r in by_mint[(wal, d["mint"])] if ds is not None and ds <= r["s"] <= ds + 60 and r["sig"] not in psig]
            realized = sum(r["sd"] for r in tx) / 1e9 if tx else None
            ld, cls, near = L.leader_info(first["s"], srv) if first else (None, "?", None)
            dld, dcls, dnear = L.leader_info(ds, srv) if ds else (None, "?", None)
            fires.append(dict(run=run, srv=srv, t=d["t"], mint=d["mint"], dump_sig=d.get("dump_sig"), ds=ds, di=di, min_out=d.get("min_out") or pk.get("min_out"),
                              spend=(pk.get("spend") or cfg.get("spend") or 0) / 1e9, guard=cfg.get("guard"), hold=cfg.get("hold"),
                              eng_client=d.get("client"), eng_leader=d.get("leader"), m2=dmp.get("m2"), drop=dmp.get("drop_pct"), sell=dmp.get("sell"),
                              dvsol=dmp.get("vsol"), dvtok=dmp.get("vtok"), ncopies=len(d["sigs"]), nlanded=len(landed),
                              us=(first["s"], first["i"]) if first else None, us_err=(first["err"] if first else None),
                              fill_pos=(fill["s"], fill["i"]) if fill else None, out=out, buy_cost=buy_cost,
                              land_leader=ld, land_client=cls, land_near=near, dump_leader=dld, dump_client=dcls, dump_near=dnear,
                              ntx=len(tx), realized=realized, sell_cost=sum(r["fee"] + r["tips"] for r in tx if r["sell"]) / 1e9 if tx else None,
                              decision_us=d.get("decision_us")))
        print(run, "fires", len(F), "presend attempts", len(patt), "landed", len(pland), flush=True)
    pickle.dump(fires, open(f"{L.D}/live_fires.pkl", "wb")); pickle.dump(pres, open(f"{L.D}/live_presend.pkl", "wb"))
    c = collections.Counter(f["out"] for f in fires); print("fires", len(fires), dict(c))


if __name__ == "__main__":
    main()
