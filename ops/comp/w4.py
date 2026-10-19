# READ-ONLY offline. 4yFAz: per-buy features (size vs curve state), fees, exits; from /root/sizing tx.jsonl + tapes.
import json, collections, statistics as st, math, glob, sys
sys.path.insert(0, "/root/comp")
from lib import NODES
W = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
V0, T0 = 30_000_000_000, 1_073_000_000_000_000
K = V0 * T0
RENT = 2039280
TX = [json.loads(l) for l in open("/root/sizing/tx.jsonl")]
TAPE = {}
for fn in glob.glob("/root/sizing/tape*.jsonl"):
    for l in open(fn):
        try: r = json.loads(l)
        except Exception: continue
        if "tape" in r and r["mint"] not in TAPE: TAPE[r["mint"]] = r
SOLPX = json.load(open("/root/solprice.json")).get("price", 104) if True else 104
TIERS = [0.49, 0.721, 1.171, 1.432, 2.153, 2.926]
by = collections.defaultdict(lambda: {"ok": [], "fail": []})
for t in TX:
    mine = [e for e in t["ev"] if e["user"] == W]
    if not t["err"] and mine: by[mine[0]["mint"]]["ok"].append(t)
    elif t["err"]:
        for m in t["mints"]: by[m]["fail"].append(t)

def sysxf(t):
    out = []
    for ix in t["ixs"]:
        if ix["p"] == "11111111111111111111111111111111" and ix["d"].startswith("02000000") and len(ix["acc"]) >= 2:
            out.append((ix["acc"][1], int.from_bytes(bytes.fromhex(ix["d"][8:24]), "little")))
    return out

rows = []
for m, v in by.items():
    if not v["ok"]: continue
    okt = sorted(v["ok"], key=lambda t: (t["slot"], t["bt"] or 0))
    evs = [(t, e) for t in okt for e in t["ev"] if e["user"] == W and e["mint"] == m]
    buys = [(t, e) for t, e in evs if e["buy"]]
    sells = [(t, e) for t, e in evs if not e["buy"]]
    if not buys or buys[0][1]["sol"] == 0: continue
    t0, e0 = buys[0]
    f = dict(mint=m, slot=t0["slot"], bt=t0["bt"], sol=e0["sol"] / 1e9, tok=e0["tok"])
    f["tier"] = min(TIERS, key=lambda x: abs(x - f["sol"])) if min(abs(x - f["sol"]) for x in TIERS) < 0.02 else None
    vp, tp = e0["vsol"] - e0["sol"], e0["vtok"] + e0["tok"]
    f["vsol_pre"] = vp / 1e9; f["real_pre"] = (vp - V0) / 1e9; f["mc_pre"] = vp / tp * 1e6; f["mc_usd"] = f["mc_pre"] * SOLPX
    f["impact"] = (e0["vsol"] / e0["vtok"]) / (vp / tp) - 1
    f["size_pct_vsol"] = e0["sol"] / vp
    f["cu"] = t0["cu_price"]; f["cul"] = t0["cu_limit"]; f["txfee"] = t0["fee"] / 1e9
    f["prio"] = ((t0["cu_price"] or 0) * (t0["cu_limit"] or 0) / 1e6) / 1e9
    f["tips"] = [(x[0], x[1] / 1e9, x[2]) for x in t0["tips"]]
    f["tip"] = sum(x[1] for x in t0["tips"]) / 1e9
    f["xf"] = [(d[:8], a / 1e9) for d, a in sysxf(t0)]
    f["land"] = f["txfee"] + f["tip"]
    f["land_pct"] = f["land"] / f["sol"]
    f["progs"] = [ix["p"][:6] for ix in t0["ixs"]]
    f["nsell"] = len(sells)
    f["sell_tok_frac"] = [e["tok"] / max(1, sum(x["tok"] for _, x in buys)) for _, e in sells]
    f["sell_dslots"] = [t["slot"] - t0["slot"] for t, _ in sells]
    f["sell_px_ratio"] = [(e["sol"] / max(1, e["tok"])) / (e0["sol"] / e0["tok"]) for _, e in sells]
    f["sold_frac"] = sum(e["tok"] for _, e in sells) / max(1, sum(e["tok"] for _, e in buys))
    dsum = sum(t["dsol"] for t in okt) + RENT - sum(t["fee"] for t in v["fail"])
    f["pnl"] = dsum / 1e9
    cost = sum(e["sol"] for _, e in buys) / 1e9
    f["pnl_pct"] = f["pnl"] / cost
    f["nfail"] = len(v["fail"])
    # sell fees
    f["sell_land"] = [t["fee"] / 1e9 + sum(x[1] for x in t["tips"]) / 1e9 for t, _ in sells]
    f["sell_cu"] = [t["cu_price"] for t, _ in sells]
    tpd = TAPE.get(m)
    if tpd and tpd.get("tape"):
        rws = tpd["tape"]
        cs = tpd["cslot"]; f["cslot"] = cs; f["dslot"] = t0["slot"] - cs
        ld = tpd.get("leaders") or []
        f["lc"] = ld[t0["slot"] - cs][1] if 0 <= t0["slot"] - cs < len(ld) else "?"
        ci = next((i for i, r in enumerate(rws) if r["create"]), None)
        if ci is not None:
            cr = rws[ci]; creator = cr["creator"]
            f["dev"] = sum(e[2] for e in cr["ev"] if e[0]) / 1e9
            f["create_tips"] = [(x[0], x[1] / 1e9) for x in cr["tips"]]
            f["moon"] = any(True for x in cr.get("tips", []) if str(x[0]).startswith("lunar"))
            gl, gs, gw, li = 0, 0, {creator, cr["payer"]}, cr["i"]
            j = ci + 1
            while j < len(rws) and rws[j]["slot"] == cr["slot"] and rws[j]["i"] == li + 1 and rws[j]["ok"] and any(e[0] for e in rws[j]["ev"]):
                gl += 1; gs += sum(e[2] for e in rws[j]["ev"] if e[0]); gw.add(rws[j]["payer"]); gw |= {e[1] for e in rws[j]["ev"]}
                li = rws[j]["i"]; j += 1
            f["glued"] = gl; f["gsol"] = gs / 1e9
            base_v = (cr["ev"][-1][4] if cr["ev"] else V0)
            pbv = rws[j - 1]["ev"][-1][4] if gl and rws[j - 1]["ev"] else base_v
            pbt = rws[j - 1]["ev"][-1][5] if gl and rws[j - 1]["ev"] else (cr["ev"][-1][5] if cr["ev"] else T0)
            f["px_vs_pb"] = (vp / tp) / (pbv / pbt)
            hi = next((i for i, r in enumerate(rws) if r["his"] and r["ok"] and any(e[0] and e[1] == W for e in r["ev"])), None)
            if hi is not None:
                hr = rws[hi]
                f["pos"] = hr["i"] - cr["i"] if hr["slot"] == cr["slot"] else None
                ahead = [r for r in rws[j:hi] if r["ok"]]
                ob = [e for r in ahead for e in r["ev"] if e[1] not in gw and e[1] != W and e[0]]
                f["n_out_ahead"] = len({e[1] for e in ob}); f["sol_out_ahead"] = sum(e[2] for e in ob) / 1e9
                # sell context: for each of his sells, what happened in the prior 1/3/10 s (2.5 slots/s) and price path
                path = []  # (slot, idx, px, user, buy, sol)
                for r in rws[hi:]:
                    if not r["ok"]: continue
                    for e in r["ev"]:
                        path.append((r["slot"], r["i"], e[4] / e[5], e[1], e[0], e[2] / 1e9))
                entry_px = e0["vsol"] / e0["vtok"]
                ctx = []
                for ts, es in sells:
                    k = next((n for n, p in enumerate(path) if p[0] == ts["slot"] and p[3] == W and not p[4]), None)
                    if k is None: continue
                    pre = path[:k]
                    pk = max([p[2] for p in pre] or [entry_px])
                    cur = pre[-1][2] if pre else entry_px
                    def win(sl):
                        lo = ts["slot"] - sl
                        w = [p for p in pre if p[0] >= lo and p[3] != W]
                        return dict(nb=sum(1 for p in w if p[4]), ns=sum(1 for p in w if not p[4]), bsol=sum(p[5] for p in w if p[4]), ssol=sum(p[5] for p in w if not p[4]),
                                    big_sell=max([p[5] for p in w if not p[4]] or [0]), bundle_sell=sum(p[5] for p in w if not p[4] and p[3] in gw))
                    ctx.append(dict(dslot=ts["slot"] - t0["slot"], px_vs_entry=cur / entry_px, peak_vs_entry=pk / entry_px, dd_from_peak=cur / pk - 1,
                                    w1=win(3), w3=win(8), w10=win(25), frac=es["tok"] / max(1, e0["tok"])))
                f["sell_ctx"] = ctx
    rows.append(f)
json.dump(rows, open("/root/comp/w4_rows.json", "w"))
print("4yFAz first buys", len(rows), "with tape", sum(1 for r in rows if "dev" in r), "with pos", sum(1 for r in rows if r.get("pos") is not None or "n_out_ahead" in r))
