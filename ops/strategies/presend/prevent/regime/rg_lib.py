"""REGIME shared loader: per-run live trade sequences (MEASURED from the engine records), windows with their failed-try fees,
shadow row exits (PAPER) and market-wide dump events. Times are unix seconds; P&L in SOL.
Scaling to 0.696 SOL (the current T2 size): scaled = (pnl + FIX) * 0.696 / spend - FIX, FIX = 2.0 mSOL of per-trade fixed costs
(buy fee + tip + sell fee + sell tips; MEASURED ~2.0 mSOL r37), rent (ATA close refund) and failed-try fees are not scaled."""
import pickle, glob, collections, datetime as dt
X = "/home/it/sniper-data/prevent/regime/x"
PKT = dt.timezone(dt.timedelta(hours=5))
FIX = 0.0020
SIZE = 0.696
LIVE_ORDER = ["dip_r21", "dip_r22", "dip_r23", "dip_r24", "dip_r26", "dip_r27", "dip_r28",
              "dip_ams_r16", "dip_ams_r17", "dip_ams_r19", "dip_ams_r20", "dip_ams_r24", "dip_ams_r25", "dip_ams_r26", "dip_ams_r27",
              "dip_ams_r34", "dip_ams_r35", "dip_ams_r36", "dip_ams_r37", "dip_ams_r38"]
SHADOW_ORDER = ["dip_ams_r14", "dip_ams_r15", "dip_ams_r21", "dip_ams_r22", "dip_ams_r23", "dip_r15", "dip_r16", "dip_r20", "dip_r25"]
PICK = [r for r in LIVE_ORDER if r not in ("dip_ams_r37", "dip_ams_r38")]
TEST = ["dip_ams_r37"]


def short(name):
    return ("AMS " if "ams" in name else "FRA ") + name.split("_")[-1]


def pkt(t, fmt="%m-%d %H:%M"):
    return dt.datetime.fromtimestamp(t, PKT).strftime(fmt)


def load(name):
    return pickle.load(open(f"{X}/{name}.pkl", "rb"))


def scale(pnl, spend):
    if not spend:
        return pnl
    return (pnl + FIX) * SIZE / spend - FIX


def live_run(name):
    """returns dict: trades (time-ordered list), windows (all live arms incl. filled) and the run span"""
    o = load(name)
    fills = collections.defaultdict(list)
    for f in o["fills"]:
        fills[(f["w"], f["mint"])].append(f)
    closes = collections.defaultdict(list)
    for c in o["closes"]:
        closes[(c["w"], c["mint"])].append(c)
    ata = collections.defaultdict(list)
    for a in o["ata"]:
        if a.get("ok"):
            ata[a["mint"]].append(a["delta"] or 0)
    trades = []
    for r in o["realized"]:
        k = (r["w"], r["mint"])
        f = fills.get(k)
        if not f:
            continue
        f = f[0]
        c = closes.get(k, [{}])[0]
        rent = ata[r["mint"]].pop(0) / 1e9 if ata.get(r["mint"]) else 0.0
        spend = (f.get("spend") or c.get("spend") or 0) / 1e9
        pnl = r["pnl"] / 1e9
        t = f["t"] / 1e9
        st = (c.get("sell_t") or 0) / 1e9 or t + (c.get("held") or 1.0)
        fee = o["fees"].get(r["w"], [0, 0, None])[0] / 1e9
        trades.append(dict(run=name, t=t, st=max(st, t), w=r["w"], kind=r["kind"], mint=r["mint"], pnl=pnl, rent=rent, spend=spend,
                           why=c.get("why"), wfee=fee, s=scale(pnl, spend)))
    trades.sort(key=lambda x: x["t"])
    filled_w = {x["w"] for x in trades}
    wins = []
    for a in o["arms"]:
        if a["t"] is None:
            continue
        fee = o["fees"].get(a["w"], [0, 0, None])[0] / 1e9
        wins.append(dict(t=a["t"] / 1e9, w=a["w"], kind=a["kind"], mint=a["mint"], fee=fee, filled=a["w"] in filled_w))
    wins.sort(key=lambda x: x["t"])
    t0 = (o["sessions"][0][0] if o["sessions"] and o["sessions"][0][0] else o["first_t"]) / 1e9
    t1 = o["last_t"] / 1e9
    # failed-try fees of windows without an arm record (should be none)
    armed_w = {a["w"] for a in o["arms"]}
    lost_fee = sum(v[0] for w, v in o["fees"].items() if w not in armed_w) / 1e9
    return dict(name=name, trades=trades, wins=wins, t0=t0, t1=t1, cfg=o["cfg"], stops=o["stops"], lost_fee=lost_fee, o=o)


def shadow_seq(o, row="c", min_age=2):
    """PAPER: the engine's shadow row exits in time order, (t, pnl SOL at the shadow size, why); windows with a known trigger age
    below min_age are dropped (the live engine skips them)."""
    age = {}
    for a in o["sh_arms"]:
        age[(a["w"], a["mint"])] = a["age"]
    out = []
    for x in o["sh_exits"]:
        if x["row"] != row or x.get("t") is None or x["pnl"] is None:
            continue
        ag = age.get((x["w"], x["mint"]))
        if min_age and ag is not None and ag < min_age:
            continue
        out.append(dict(t=x["t"] / 1e9, pnl=x["pnl"], why=x["why"], mint=x["mint"]))
    out.sort(key=lambda z: z["t"])
    return out
