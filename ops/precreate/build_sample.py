#!/usr/bin/env python3
"""Build the combined launch sample: unbiased population (creates+trajectories) + his picks (his_500).
Each row: mint, creator, create_slot, is_his, entry_px, series([slot,px]), plus create flags for filtering."""
import json

CRE = json.load(open("/root/profit_backtest/creates.json"))
TRAJ = {t["mint"]: t for t in json.load(open("/root/profit_backtest/trajectories.json"))}
HIS = json.load(open("/root/last500/his_500.json"))
FEAT = {f["mint"]: f for f in json.load(open("/root/last500/feat_500.json"))}


def norm_series(ser):
    out = []
    for row in ser or []:
        if len(row) >= 3:
            out.append([row[0], row[-1]])   # [slot, bt, px] -> [slot, px]
        elif len(row) == 2:
            out.append([row[0], row[1]])
    return out


sample = []
seen = set()

# population (unbiased), only those with a usable entry px / trajectory
for c in CRE:
    t = TRAJ.get(c["mint"])
    if not t or not t.get("entry_px"):
        continue
    sample.append({
        "mint": c["mint"], "creator": c["creator"], "create_slot": c["create_slot"],
        "is_his": False, "entry_px": t["entry_px"], "series": norm_series(t.get("series")),
        "dev_buy": c.get("dev_buy", 0.0), "dev_buy_wire": c.get("dev_buy_wire", 0.0),
        "creator_fee_bps": c.get("creator_fee_bps", 0), "mayhem": c.get("mayhem", 0),
        "holder_reward": c.get("holder_reward", 0), "cashback": c.get("cashback", 0),
        "cosnipers": t.get("cosnipers", 0),
    })
    seen.add(("pop", c["mint"]))

# his picks
for h in HIS:
    if not h.get("entry_px"):
        continue
    f = FEAT.get(h["mint"], {})
    ser = norm_series(f.get("series") or h.get("series"))
    sample.append({
        "mint": h["mint"], "creator": h["creator"], "create_slot": h["create_slot"],
        "is_his": True, "entry_px": h["entry_px"], "series": ser,
        "dev_buy": h.get("dev_buy", 0.0), "dev_buy_wire": h.get("dev_buy_wire", 0.0),
        "creator_fee_bps": h.get("creator_fee_bps", 0), "mayhem": h.get("mayhem", 0),
        "holder_reward": h.get("holder_reward", 0), "cashback": h.get("cashback", 0),
        "cosnipers": h.get("cosnipers_slot0", 0),
        "his_net_R": h.get("net_R"),
    })

json.dump(sample, open("/root/precreate/sample.json", "w"))
npop = sum(1 for s in sample if not s["is_his"])
nhis = sum(1 for s in sample if s["is_his"])
nser_pop = sum(1 for s in sample if not s["is_his"] and s["series"])
nser_his = sum(1 for s in sample if s["is_his"] and s["series"])
print("sample: %d total  pop=%d (with series %d)  his=%d (with series %d)" % (
    len(sample), npop, nser_pop, nhis, nser_his))
