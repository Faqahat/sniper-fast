#!/usr/bin/env python3
"""GAP step 2 (read-only): every live run record (AMS r9-r33, FRA r1-r26) reduced to what the ledger needs.
Per run: window, mode (regular live / pre-send live / probe-only), and
  dumps   {(mint, slot): [(idx, sig, pass, m2_pick, launch_ok, dev, sell, drop, age, t)]}  (only in-envelope dumps are logged)
  pick    {dump sig: (client, leader)}; skip {dump sig: why}; fire {dump sig: [our buy sigs]}
  arms    [(mint, whale, trig slot, en slot, end slot, end why, filled, t)]   (pre-send LIVE arms; end = disarm)
  pskips  [(mint, whale, trig slot, why, t)]                                    (pre-send LIVE skips)
  patt    [(sig, mint, slot, idx, res, d_slot, d_idx, d_user8, t)]              (pre-send attempts that landed / resolved)
  sigs_reg / sigs_ps: our tx signatures by path (buys, sells, ATA closes) to split our wallet txs.
Out: /home/moiz/sniper-data/haqq_dissect/gap/g2_engine.pkl"""
import json, pickle, sys, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
from runs import run_files
OUT = "/home/moiz/sniper-data/haqq_dissect/gap"


def tsec(t): return t / 1e9 if t and t > 1e15 else t


def main():
    R = {}
    for run, f in run_files().items():
        X = dict(srv=run[:3], start=None, end=None, cfg=None, dumps=collections.defaultdict(list), pick={}, skip={}, fire={}, close={},
                 arms=[], pskips=[], patt=[], pfills=[], pclose=[], sigs_reg=set(), sigs_ps=set(), n_probe=0, n_fire=0, n_patt=0)
        armi = {}
        for l in open(f):
            try: d = json.loads(l)
            except Exception: continue
            e = d.get("ev"); t = tsec(d.get("t"))
            if t and t > 1.7e9:
                X["start"] = X["start"] or t; X["end"] = t
            if e == "run_start" and X["cfg"] is None: X["cfg"] = d
            elif e == "dump":
                X["dumps"][(d["mint"], d["slot"])].append((d["idx"], d["sig"], d.get("pass"), d.get("m2_pick"), d.get("launch_ok"), d.get("dev"),
                                                            d.get("sell"), d.get("drop_pct"), d.get("age"), t))
            elif e == "pick": X["pick"][d["sig"]] = (d.get("client"), d.get("leader"))
            elif e == "pick_skip": X["skip"][d["sig"]] = d.get("why")
            elif e == "fire":
                sigs = [d["buy_sig"]] + [p["sig"] for p in (d.get("nonce") or {}).get("per_path", []) if p.get("sig")] + [v["sig"] for v in d.get("variants", []) if v.get("sig")]
                X["fire"][d.get("dump_sig")] = sigs; X["sigs_reg"].update(sigs); X["n_fire"] += 1
            elif e == "close":
                X["close"][d.get("buy_sig")] = dict(result=d.get("result"), mint=d.get("mint"), dump_slot=d.get("dump_slot"), dump_idx=d.get("dump_idx"),
                                                    dump_sig=d.get("dump_sig"), pnl=d.get("curve_pnl"))
                for s in d.get("sell_sigs") or []:
                    X["sigs_reg"].add(s[0] if isinstance(s, list) else s)
            elif e in ("probe",): X["n_probe"] += 1
            elif e == "presend_live_arm":
                tr = d["trig"]; key = (tr["mint"], tr["slot"])
                armi[key] = len(X["arms"])
                X["arms"].append([tr["mint"], tr.get("wallet"), tr["slot"], d.get("en_slot"), None, None, None, t, tr.get("pct"), bool(d.get("dry"))])
            elif e == "presend_live_disarm":
                key = (d["mint"], d.get("trig_slot"))
                if key in armi:
                    a = X["arms"][armi[key]]; a[4] = d.get("slot"); a[5] = d.get("why"); a[6] = d.get("filled")
            elif e == "presend_live_skip":
                tr = d.get("trig") or {}
                X["pskips"].append((tr.get("mint"), tr.get("wallet"), tr.get("slot"), d.get("why"), t, tr.get("pct")))
            elif e == "presend_attempt":
                X["sigs_ps"].add(d["sig"]); X["n_patt"] += 1
            elif e == "presend_attempt_land":
                dd = d.get("d") or {}
                X["patt"].append((d["sig"], d["mint"], d.get("slot"), d.get("idx"), d.get("res"), dd.get("slot"), dd.get("idx"), dd.get("user"), t))
                X["sigs_ps"].add(d["sig"])
            elif e == "presend_live_fill":
                X["pfills"].append((d["sig"], d["mint"], d["slot"], d.get("idx"), t)); X["sigs_ps"].add(d["sig"])
            elif e == "presend_live_close":
                X["pclose"].append(dict(mint=d["mint"], buy_sigs=d.get("buy_sigs") or [d.get("buy_sig")], pnl=d.get("curve_pnl"), held_s=d.get("held_s")))
                for s in d.get("sell_sigs") or []:
                    X["sigs_ps"].add(s[0] if isinstance(s, list) else s)
                for s in d.get("buy_sigs") or []: X["sigs_ps"].add(s)
            elif e == "presend_live_ata_close" and d.get("sig"): X["sigs_ps"].add(d["sig"])
        c = X["cfg"] or {}
        X["probe_run"] = X["n_probe"] > 0 and X["n_fire"] == 0
        X["ps_live"] = len(X["arms"]) > 0 or X["n_patt"] > 0
        X["m2mode"] = (c.get("m2") or {}).get("mode")
        X["dumps"] = dict(X["dumps"])
        R[run] = X
        print(run, X["srv"], int(X["start"] or 0), int(X["end"] or 0), "probe" if X["probe_run"] else "", "PS" if X["ps_live"] else "", X["m2mode"],
              "dumps", sum(len(v) for v in X["dumps"].values()), "fires", X["n_fire"], "arms", len(X["arms"]), "pskips", len(X["pskips"]),
              "patt", len(X["patt"]), "pfills", len(X["pfills"]), flush=True)
    pickle.dump(R, open(f"{OUT}/g2_engine.pkl", "wb"))


if __name__ == "__main__":
    main()
