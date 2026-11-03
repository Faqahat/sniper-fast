#!/usr/bin/env python3
"""PAPER AUDIT step 2 [MEASURED, read-only]: rebuild the engine's "PRESEND shadow" status-line numbers (src/presend.rs Shadow::line)
from the run's records, split row c by what LIVE decided on the same trigger, and compare with dipmon's paper line.

Engine formula (presend.rs:782), per row r in a / b / c (+0 / +5 / +10 ms after the crossing trade, block-position clock):
  gross[r] = sum of presend_exit.pnl (size 0.55 SOL fee-inclusive = 0.5432 SOL into the curve; pump fee both ways; no tx costs)
  net[r]   = gross[r] - exits[r] x (TIP 0.001 + 2 x FEE_CHEAP) - max(K_ABC 20 x armed_slots[r] - fills[r], 0) x FEE_CHEAP
  FEE_CHEAP = (5000 + 60,000 CU x 1,000 uL / 1e6) lamports = 5,060 lamports; armed_slots summed from presend_disarm rows.
usage: pa2_recon.py X.pkl RUN.log OUT.json"""
import sys, json, re, pickle, collections

FEE_CHEAP = (5000.0 + 60_000.0 * 1_000.0 / 1e6) / 1e9
TIP = 0.001
K_ABC = 20.0
ROWS = ("a", "b", "c")
RX = re.compile(r"PRESEND shadow: .*?triggers (\d+) armed a/b/c (\d+)/(\d+)/(\d+) fills (\d+)/(\d+)/(\d+) exits (\d+)/(\d+)/(\d+) gross ([-+]?[\d.]+)/([-+]?[\d.]+)/([-+]?[\d.]+) SOL "
                r"net\(cheap, 20/slot\) ([-+]?[\d.]+)/([-+]?[\d.]+)/([-+]?[\d.]+)")


def last_status(log):
    last = None
    for line in open(log, errors="replace"):
        if "PRESEND shadow:" in line and "DIP status" in line:
            m = RX.search(line)
            if m: last = m
    if last is None: return None
    g = [float(x) for x in last.groups()]
    return {"triggers": int(g[0]), "armed": g[1:4], "fills": g[4:7], "exits": g[7:10], "gross": g[10:13], "net": g[13:16]}


def live_decision(X):
    """trigger (sig, j) -> what live did: 'armed' or the skip reason"""
    dec = {}
    for k, a in X["lv_arm"].items():
        if a.get("kind") == "rearm": continue
        tg = a["trig"]; dec[(tg["sig"], tg.get("j", 0))] = ("armed", k)
    for s in X["lv_skip"]:
        if s.get("kind") == "rearm" or "trig" not in s: continue
        tg = s["trig"]; dec.setdefault((tg["sig"], tg.get("j", 0)), (s.get("why") or ("quiet" if s.get("quiet_skip") else "?"), None))
    return dec


def recon(X):
    ses = max(k[0] for k in X["sh_arm"])
    out = {"session": ses}
    arms = {k: v for k, v in X["sh_arm"].items() if k[0] == ses}
    dis = {k: v for k, v in X["sh_dis"].items() if k[0] == ses}
    rows = {}
    for r in ROWS:
        fills = [v for k, v in X["sh_fill"].items() if k[0] == ses and k[2] == r]
        exits = [v for k, v in X["sh_exit"].items() if k[0] == ses and k[2] == r]
        armed = sum(1 for d in dis.values() if d["rows"][r]["armed"] is True)
        slots = sum(d["rows"][r]["slots"] for d in dis.values() if d["rows"][r]["armed"] is True)
        gross = sum(e["pnl"] for e in exits)
        tipfee = len(exits) * (TIP + 2 * FEE_CHEAP)
        failed_n = max(K_ABC * slots - len(fills), 0.0)
        failed = failed_n * FEE_CHEAP
        rows[r] = {"armed_disarmed": armed, "armed_slots": slots, "fills": len(fills), "exits": len(exits), "gross": gross, "tips": len(exits) * TIP,
                   "tx_fees": len(exits) * 2 * FEE_CHEAP, "failed_tries": failed_n, "failed_fees": failed, "net": gross - tipfee - failed,
                   "net_cheap_sum": sum(e["net_cheap"] for e in exits), "win": sum(1 for e in exits if e["pnl"] > 0),
                   "mean_pnl_mSOL": 1e3 * gross / max(len(exits), 1)}
    out["rows"] = rows
    out["triggers_records"] = len(arms)
    # row c split by the live decision on the same trigger
    dec = live_decision(X)
    split = collections.defaultdict(lambda: {"windows": 0, "armed_c": 0, "slots_c": 0, "fills_c": 0, "gross_c": 0.0, "net_cheap_c": 0.0, "fills_a": 0, "gross_a": 0.0})
    for k, a in arms.items():
        d = dec.get((a["sig"], a.get("j", 0)), ("no_live_record", None))[0]
        S = split[d]; S["windows"] += 1
        dd = dis.get(k)
        if dd and dd["rows"]["c"]["armed"] is True: S["armed_c"] += 1; S["slots_c"] += dd["rows"]["c"]["slots"]
        e = X["sh_exit"].get((k[0], k[1], "c"))
        if e: S["fills_c"] += 1; S["gross_c"] += e["pnl"]; S["net_cheap_c"] += e["net_cheap"]
        e = X["sh_exit"].get((k[0], k[1], "a"))
        if e: S["fills_a"] += 1; S["gross_a"] += e["pnl"]
    for d, S in split.items():
        S["failed_fees_c"] = max(K_ABC * S["slots_c"] - S["fills_c"], 0) * FEE_CHEAP
        S["net_engine_c"] = S["net_cheap_c"] - S["failed_fees_c"]
    out["row_c_by_live_decision"] = dict(sorted(split.items(), key=lambda kv: -kv[1]["windows"]))
    # live, same run
    lv = {"armed_windows": sum(1 for a in X["lv_arm"].values() if a.get("kind") != "rearm"), "rearm_windows": sum(1 for a in X["lv_arm"].values() if a.get("kind") == "rearm"),
          "fills": sum(len(v) for v in X["lv_fill"].values()), "realized": sum((r.get("pnl") or 0) for v in X["lv_real"].values() for r in v) / 1e9,
          "rent_back": sum((r.get("delta") or 0) for r in X["lv_ata_close"] if r.get("ok")) / 1e9}
    tries = [a for v in X["tries"].values() for a in v]
    landed_failed = [a for a in tries if a["land"] and a["land"].get("res") not in (None, "unseen", "ok")]
    lv["tries_unique"] = len(tries); lv["tries_landed_failed"] = len(landed_failed)
    lv["failed_fees"] = sum((a["land"].get("fee") or 0) for a in landed_failed) / 1e9
    lv["net_cash"] = lv["realized"] + lv["rent_back"] - lv["failed_fees"]
    out["live"] = lv
    return out


if __name__ == "__main__":
    X = pickle.load(open(sys.argv[1], "rb"))
    st = last_status(sys.argv[2])
    R = recon(X); R["status_line"] = st
    json.dump(R, open(sys.argv[3], "w"), indent=1, default=str)
    print("last status line:", st)
    for r, v in R["rows"].items():
        print(f"row {r}: armed {v['armed_disarmed']} slots {v['armed_slots']} fills {v['fills']} exits {v['exits']} gross {v['gross']:+.3f} tips {v['tips']:.3f} "
              f"txfees {v['tx_fees']:.4f} failed tries {v['failed_tries']:.0f} = {v['failed_fees']:.3f} SOL -> net {v['net']:+.3f} | win {v['win']} mean {v['mean_pnl_mSOL']:+.2f} mSOL")
    print("row c by live decision:")
    for d, S in R["row_c_by_live_decision"].items():
        print(f"  {d:22s} windows {S['windows']:5d} armed_c {S['armed_c']:5d} slots {S['slots_c']:6d} fills_c {S['fills_c']:4d} gross_c {S['gross_c']:+.3f} "
              f"net_cheap_c {S['net_cheap_c']:+.3f} failed {S['failed_fees_c']:.3f} -> engine-style net {S['net_engine_c']:+.3f} | row a fills {S['fills_a']} gross {S['gross_a']:+.3f}")
    print("live:", R["live"])
