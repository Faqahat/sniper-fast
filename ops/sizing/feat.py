# READ-ONLY offline. Build per-buy features (feat.jsonl) and per-sell rows (sells.jsonl) from tx.jsonl + tape.jsonl.
import json, collections, math
W = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
D = "/root/sizing/"
V0, T0 = 30_000_000_000, 1_073_000_000_000_000
K = V0 * T0
RENT = 2039280
TX = [json.loads(l) for l in open(D + "tx.jsonl")]
TAPE = {}
import glob
for fn in glob.glob(D + "tape*.jsonl"):
    if "old" in fn: continue
    for l in open(fn):
        try: r = json.loads(l)
        except Exception: continue
        if "tape" in r: TAPE[r["mint"]] = r
sol_px = 0
try: sol_px = json.load(open("/root/solprice.json")).get("price", 0)
except Exception: pass

by = collections.defaultdict(lambda: {"ok": [], "fail": []})
for t in TX:
    mine = [e for e in t["ev"] if e["user"] == W]
    if not t["err"] and mine:
        by[mine[0]["mint"]]["ok"].append(t)
    elif t["err"]:
        for m in t["mints"]:
            by[m]["fail"].append(t)

def decode(t):
    for ix in t["ixs"]:
        d = bytes.fromhex(ix["d"]); p = ix["p"]
        if p.startswith("6EF8rr") and len(d) >= 24 and d[:8].hex() == "e1f7501ed5b38488":
            return {"prog": "pump_v3", "spend": int.from_bytes(d[8:16], "little"), "min_out": int.from_bytes(d[16:24], "little")}
        if p.startswith("BehnpC") and len(d) >= 16:
            return {"prog": "Behnp", "spend": int.from_bytes(d[0:8], "little"), "min_out": int.from_bytes(d[8:16], "little")}
        if p.startswith("2YAbTp") and len(d) >= 56:
            u = [int.from_bytes(d[i:i + 8], "little") for i in range(0, 56, 8)]
            return {"prog": "2YAb", "args": u, "tail": d[56:].hex()}
    return {"prog": "?"}

def lh_slot(t):
    for ix in t["ixs"]:
        if ix["p"].startswith("L2TExM"):
            d = bytes.fromhex(ix["d"])
            if len(d) >= 12 and d[0] == 0x0f: return int.from_bytes(d[3:11], "little"), d[11]
    return None

feats, sells = [], []
for m, v in by.items():
    if not v["ok"]: continue
    okt = sorted(v["ok"], key=lambda t: (t["slot"], t["bt"] or 0))
    evs = []
    for t in okt:
        for e in t["ev"]:
            if e["user"] == W and e["mint"] == m: evs.append((t, e))
    buys = [(t, e) for t, e in evs if e["buy"]]
    if not buys or buys[0][1]["sol"] == 0: continue
    bt0, be0 = buys[0]
    tp = TAPE.get(m)
    f = {"mint": m, "slot": bt0["slot"], "bt": bt0["bt"], "sol": be0["sol"], "tok": be0["tok"], "nbuys": len(buys),
         "buy_sol_total": sum(e["sol"] for _, e in buys), "cu": bt0["cu_price"], "cul": bt0["cu_limit"], "fee": bt0["fee"],
         "tips": bt0["tips"], "tip_sum": sum(x[1] for x in bt0["tips"]), "wallet_out": -bt0["dsol"], "pre_bal": bt0["pre"]}
    f["vsol_pre"] = be0["vsol"] - be0["sol"]; f["vtok_pre"] = be0["vtok"] + be0["tok"]
    f["real_pre"] = f["vsol_pre"] - V0
    f["mcap_pre"] = f["vsol_pre"] / f["vtok_pre"] * 1e6  # SOL
    f["px_virgin"] = (f["vsol_pre"] / V0) ** 2  # price vs a no-dev launch
    f["fill_px"] = be0["sol"] / be0["tok"]
    f["dec"] = decode(bt0)
    ls = lh_slot(bt0); f["lh"] = ls
    # outcome
    sold = [(t, e) for t, e in evs if not e["buy"]]
    f["sell_sol"] = sum(e["sol"] for _, e in sold); f["sell_tok"] = sum(e["tok"] for _, e in sold)
    f["nsells"] = len(sold)
    dsum = sum(t["dsol"] for t in okt) + RENT  # close refund approximated
    f["fail_fee"] = sum(t["fee"] for t in v["fail"])
    f["pnl"] = dsum / 1e9
    f["pnl_pct"] = dsum / max(1, f["buy_sol_total"])
    f["hold_slots"] = (sold[-1][0]["slot"] - bt0["slot"]) if sold else None
    f["first_sell_slots"] = (sold[0][0]["slot"] - bt0["slot"]) if sold else None
    f["nfail"] = len(v["fail"])
    f["fail_codes"] = collections.Counter(json.dumps(t["err"]) for t in v["fail"]).most_common(4)
    f["fail_slip"] = sum(1 for t in v["fail"] if "6042" in json.dumps(t["err"]))
    f["fail_guard"] = sum(1 for t in v["fail"] if any("2YAbTp" in x and "0x1" in x for x in t["logs"]))
    if tp:
        rows = tp["tape"]
        f["cslot"] = tp["cslot"]; f["slot_off"] = tp["bslot"] - tp["cslot"]
        lead = {tp["cslot"] + i: c for i, (l, c) in enumerate(tp["leaders"])}
        f["client_c"] = lead.get(tp["cslot"]); f["client_b"] = lead.get(tp["bslot"])
        ci = next(i for i, r in enumerate(rows) if r["create"])
        cr = rows[ci]
        creator = cr["creator"]
        dev = sum(e[2] for e in cr["ev"] if e[0])
        base = cr["ev"][-1][4] if cr["ev"] else V0
        f["dev"] = dev; f["base"] = base; f["create_cu"] = cr["cu"]; f["create_tips"] = cr["tips"]
        # glued bundle
        gl, gsol, gw, li = 0, 0, {creator, cr["payer"]}, cr["i"]
        j = ci + 1
        while j < len(rows) and rows[j]["slot"] == cr["slot"] and rows[j]["i"] == li + 1 and rows[j]["ok"] and any(e[0] for e in rows[j]["ev"]):
            gl += 1; gsol += sum(e[2] for e in rows[j]["ev"] if e[0]); gw.add(rows[j]["payer"]); gw |= {e[1] for e in rows[j]["ev"]}
            li = rows[j]["i"]; j += 1
        f["glued"] = gl; f["gsol"] = gsol
        f["floor_mult"] = (f["vsol_pre"] / base) ** 2  # price vs post-dev floor
        f["fill_mult"] = f["fill_px"] / (base ** 2 / K)
        # his row
        hi = next((i for i, r in enumerate(rows) if r["his"] and r["ok"] and any(e[0] and e[1] == W for e in r["ev"])), None)
        f["his_found"] = hi is not None
        if hi is not None:
            hr = rows[hi]
            f["pos"] = hr["i"] - cr["i"] if hr["slot"] == cr["slot"] else None
            f["pos_in_slot"] = hr["i"]; f["nnv_slot"] = tp["nnv"].get(str(hr["slot"]))
            ahead = rows[j:hi]
            ob = [e for r in ahead if r["ok"] for e in r["ev"] if e[1] not in gw and e[1] != W]
            f["out_buy_sol_ahead"] = sum(e[2] for e in ob if e[0]); f["out_sell_sol_ahead"] = sum(e[2] for e in ob if not e[0])
            f["n_out_buys_ahead"] = sum(1 for e in ob if e[0]); f["max_out_buy_ahead"] = max([e[2] for e in ob if e[0]] or [0])
            f["bundle_sell_ahead"] = sum(e[2] for r in ahead if r["ok"] for e in r["ev"] if e[1] in gw and not e[0])
            cus = [r["cu"] or 0 for r in ahead]
            f["n_tx_ahead"] = len(ahead); f["n_fail_ahead"] = sum(1 for r in ahead if not r["ok"])
            f["max_cu_ahead"] = max(cus or [0]); f["his_copies_failed"] = sum(1 for r in rows if r["his"] and not r["ok"])
            f["n_his_rows"] = sum(1 for r in rows if r["his"])
            f["n_out_buys_slot_after"] = sum(1 for r in rows[hi + 1:] if r["slot"] == hr["slot"] and r["ok"] for e in r["ev"] if e[0])
            # sells context
            held = be0["tok"]; entry_px = f["fill_px"]
            tseq = [(r["slot"], k, r) for k, r in enumerate(rows)]
            for st, se in sold:
                si = next((k for k, r in enumerate(rows) if r["his"] and r["ok"] and r["sig"] == st["sig"][:24]), None)
                pre_v, pre_t = se["vsol"] + se["sol"], se["vtok"] - se["tok"]
                row = {"mint": m, "slot": st["slot"], "dslot": st["slot"] - bt0["slot"], "dt": (st["bt"] or 0) - (bt0["bt"] or 0),
                       "frac": se["tok"] / held if held else None, "px_vs_entry": (pre_v / pre_t) / entry_px,
                       "sell_px_vs_entry": (se["sol"] / se["tok"]) / entry_px if se["tok"] else None,
                       "real_pre": pre_v - V0, "cu": st["cu_price"], "fee": st["fee"], "tips": st["tips"], "in_tape": si is not None,
                       "ixs": [ix["p"][:6] for ix in st["ixs"]], "lh": lh_slot(st), "leg": len([1 for s2 in sells if s2["mint"] == m])}
                held -= se["tok"]
                row["frac_of_remaining_after"] = held
                if si is not None:
                    prev = rows[hi + 1:si]
                    def win(k):
                        return [r for r in prev if r["slot"] >= st["slot"] - k]
                    for k in (0, 1, 2, 5):
                        w = win(k)
                        oe = [e for r in w if r["ok"] for e in r["ev"] if e[1] != W]
                        row[f"buy_sol_{k}"] = sum(e[2] for e in oe if e[0]); row[f"sell_sol_{k}"] = sum(e[2] for e in oe if not e[0])
                        row[f"max_buy_{k}"] = max([e[2] for e in oe if e[0]] or [0])
                        row[f"bsell_{k}"] = sum(e[2] for e in oe if not e[0] and e[1] in gw)
                    oe = [e for r in prev if r["ok"] for e in r["ev"] if e[1] != W]
                    row["buyers_since"] = len({e[1] for e in oe if e[0]}); row["buy_sol_since"] = sum(e[2] for e in oe if e[0])
                    row["sell_sol_since"] = sum(e[2] for e in oe if not e[0])
                    row["bundle_sold_since"] = sum(e[2] for e in oe if not e[0] and e[1] in gw)
                    lastok = [r for r in prev if r["ok"] and r["ev"] and not r["his"]]
                    row["last_ev"] = lastok[-1]["ev"][-1][:3] if lastok else None
                    row["last_ev_slot_gap"] = st["slot"] - lastok[-1]["slot"] if lastok else None
                    row["last_is_bundle"] = (lastok[-1]["ev"][-1][1] in gw) if lastok else None
                    row["peak_since"] = max([(r["ev"][-1][4] / r["ev"][-1][5]) / entry_px for r in prev if r["ok"] and r["ev"]] or [None], key=lambda x: x or 0)
                sells.append(row)
    feats.append(f)
json.dump(feats, open(D + "feat.json", "w"))
json.dump(sells, open(D + "sells.json", "w"))
print("feats", len(feats), "with tape", sum(1 for f in feats if "dev" in f), "sells", len(sells))
