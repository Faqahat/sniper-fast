#!/usr/bin/env python3
"""READ-ONLY live-chain spot check (task 2).

For 6 launches: getTransaction(create tx), getTransaction(tx we land right after), getTransaction(last tx
before our sell); decode pump.fun TradeEvents from the RPC response (log 'Program data:' and self-CPI inner
instructions) and compare reserves/amounts with the values used from the raw collector files.
getBlock(create slot, signatures only) to confirm the in-block index ordering used for the glued bundle.
Also looks up the trades missing from the raw data (reserve-continuity breaks) via getSignaturesForAddress.
The RPC URL is read from ~/.config/sniper/ck_rpc_url and never printed. <= 4 requests/s.
Output: verify/work/rpc_check.json
"""
import base64
import json
import os
import struct
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from b58 import b58dec, b58enc  # noqa: E402
import replay as R  # noqa: E402

URL = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
TE = bytes([189, 219, 127, 211, 78, 230, 97, 238])
CPI_TAG = bytes.fromhex("e445a52e51cb9a1d")
_last = [0.0]
NCALLS = [0]


def rpc(method, params):
    dt = time.time() - _last[0]
    if dt < 0.26:
        time.sleep(0.26 - dt)
    _last[0] = time.time()
    NCALLS[0] += 1
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            out = json.loads(r.read())
    except Exception as ex:  # never leak the URL
        return {"error": {"message": str(ex).replace(URL, "<rpc>")[:200]}}
    return out


def get_tx(sig):
    r = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
    if "error" in r:
        r = rpc("getTransaction", [sig, {"encoding": "json", "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}])
    return r


def trade_events_from_tx(res, mint):
    """Return TradeEvents for mint from logs and from inner self-CPI events (deduplicated by payload)."""
    evs_log, evs_cpi = [], []
    meta = res.get("meta") or {}
    for ln in meta.get("logMessages") or []:
        if ln.startswith("Program data: "):
            for part in ln[len("Program data: "):].split():
                try:
                    b = base64.b64decode(part)
                except Exception:
                    continue
                if b[:8] == TE and b58enc(b[8:40]) == mint:
                    evs_log.append(b)
    for grp in meta.get("innerInstructions") or []:
        for ix in grp.get("instructions") or []:
            try:
                d = b58dec(ix.get("data", ""))
            except Exception:
                continue
            if d[:8] == CPI_TAG and d[8:16] == TE and b58enc(d[16:48]) == mint:
                evs_cpi.append(d[8:])
    src = evs_cpi if evs_cpi else evs_log
    out = []
    for b in src:
        sol, tok = struct.unpack_from("<QQ", b, 40)
        ts, vs, vt, rs, rt = struct.unpack_from("<qQQQQ", b, 89)
        fb = struct.unpack_from("<Q", b, 161)[0]
        cb = struct.unpack_from("<Q", b, 209)[0]
        out.append({"sol": sol, "tok": tok, "is_buy": b[56], "user": b58enc(b[57:89]), "vsol": vs, "vtok": vt,
                    "rsol": rs, "rtok": rt, "fee_bps": fb, "cfee_bps": cb})
    return out, len(evs_log), len(evs_cpi)


def cmp_tx(sig, mint, raw_events):
    r = get_tx(sig)
    if "error" in r or not r.get("result"):
        return {"sig": sig, "ok": False, "error": (r.get("error") or {}).get("message", "null result")}
    res = r["result"]
    evs, nlog, ncpi = trade_events_from_tx(res, mint)
    fields = ("sol", "tok", "is_buy", "user", "vsol", "vtok", "rsol", "rtok", "fee_bps", "cfee_bps")
    raw = [{f: e[f] for f in fields} for e in raw_events]
    eq = (len(evs) == len(raw)) and all(all(a[f] == b[f] for f in fields) for a, b in zip(evs, raw))
    return {"sig": sig, "ok": True, "slot_rpc": res.get("slot"), "slot_raw": raw_events[0]["s"] if raw_events else None,
            "blockTime_rpc": res.get("blockTime"), "err_rpc": (res.get("meta") or {}).get("err"),
            "n_events_rpc": len(evs), "n_events_raw": len(raw), "events_log": nlog, "events_cpi": ncpi,
            "all_fields_equal": eq,
            "rpc_reserves": [(e["vsol"], e["vtok"]) for e in evs], "raw_reserves": [(e["vsol"], e["vtok"]) for e in raw_events]}


def main():
    res = {x["mint"]: x for x in json.load(open(R.RESULT))}
    chain = R.load_chain()
    L0 = R.load_launches(set(res))
    picks = [("CQujDSKR", "75"), ("Hc5sxDEh", "75"), ("FkNS4X12", "75"), ("3nJzJCM2", "75"), ("7u1ydjJj", "75"), ("24nTChMf", "45")]
    report = {"spot": [], "block_order": [], "missing_trades": []}
    for pre, L in picks:
        m = next(k for k in res if k.startswith(pre))
        x = res[m]
        tr = chain[m]["trades"]
        info = L0[m][0]
        land = x["land"][L]
        ent = {"mint": m, "L": L, "file_pnl": land["pnl"], "checks": {}}
        for tag, sig in (("create", x["create_sig"]), ("after", land["after_sig"]), ("sell_after", land.get("sell_after_sig"))):
            if not sig:
                continue
            raw_ev = [t for t in tr if t["sig"] == sig]
            ent["checks"][tag] = cmp_tx(sig, m, raw_ev)
        report["spot"].append(ent)
        # in-block ordering of create slot
        b = rpc("getBlock", [info["slot"], {"encoding": "json", "transactionDetails": "signatures", "rewards": False,
                                            "maxSupportedTransactionVersion": 0, "commitment": "confirmed"}])
        if "error" in b or not b.get("result"):
            report["block_order"].append({"mint": m, "ok": False, "error": (b.get("error") or {}).get("message")})
        else:
            sigs = b["result"]["signatures"]
            idx = {s: k for k, s in enumerate(sigs)}
            cs_tr = [t for t in tr if t["s"] == info["slot"]]
            pairs = []
            seen = set()
            for t in cs_tr:
                if t["sig"] in seen:
                    continue
                seen.add(t["sig"])
                pairs.append((t["sig"][:10], t["i"], idx.get(t["sig"])))
            report["block_order"].append({"mint": m, "ok": True, "slot": info["slot"], "n_sigs_in_block": len(sigs),
                                          "create_idx_raw": info["idx"], "create_idx_rpc": idx.get(info["sig"]),
                                          "trades_in_create_slot_raw_vs_rpc_index": pairs,
                                          "all_equal": all(a == b for _, a, b in pairs) and idx.get(info["sig"]) == info["idx"]})
        print("spot", pre, json.dumps({k: (v["all_fields_equal"] if v.get("ok") else v) for k, v in ent["checks"].items()}),
              "block", report["block_order"][-1].get("all_equal"), flush=True)

    # missing trades (raw reserve continuity breaks) - find them on chain
    for pre in ("5Y7mzPwN", "Htfy9hg6", "Hc5sxDEh", "4RzBrX3M"):
        m = next(k for k in res if k.startswith(pre))
        tr = chain[m]["trades"]
        cr = chain[m]["creates"][0]
        bc = cr["bonding_curve"] if "bonding_curve" in cr else None
        # locate the break
        brk = None
        for j in range(1, len(tr)):
            a, b_ = tr[j - 1], tr[j]
            pv = b_["vsol"] - b_["sol"] if b_["is_buy"] else b_["vsol"] + b_["sol"]
            pt = b_["vtok"] + b_["tok"] if b_["is_buy"] else b_["vtok"] - b_["tok"]
            if (pv, pt) != (a["vsol"], a["vtok"]):
                brk = j
                break
        if brk is None:
            continue
        lo_t, hi_t = tr[brk - 1], tr[brk]
        known = {t["sig"] for t in tr}
        r = rpc("getSignaturesForAddress", [bc, {"before": hi_t["sig"], "limit": 40, "commitment": "confirmed"}])
        cand = []
        if "error" not in r and r.get("result"):
            for e in r["result"]:
                if e["slot"] < lo_t["s"]:
                    break
                if e["signature"] in known or e.get("err") is not None:
                    continue
                cand.append(e)
        found = []
        for e in cand[:6]:
            t = get_tx(e["signature"])
            if "error" in t or not t.get("result"):
                continue
            evs, nlog, ncpi = trade_events_from_tx(t["result"], m)
            for ev in evs:
                found.append({"sig": e["signature"], "slot": e["slot"], "slot_off_from_create": e["slot"] - tr[0]["s"],
                              "is_buy": ev["is_buy"], "sol": ev["sol"] / 1e9, "user": ev["user"], "vsol_after": ev["vsol"],
                              "vtok_after": ev["vtok"]})
        report["missing_trades"].append({"mint": m, "break_between": [lo_t["sig"], hi_t["sig"]],
                                         "slots": [lo_t["s"], hi_t["s"]], "candidates_unknown_successful": len(cand),
                                         "found_trade_events": found})
        print("missing", pre, json.dumps(found)[:600], flush=True)
    report["rpc_calls"] = NCALLS[0]
    json.dump(report, open(os.path.join(HERE, "work", "rpc_check.json"), "w"), indent=1)
    print("rpc calls", NCALLS[0])


if __name__ == "__main__":
    main()
