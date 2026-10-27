#!/usr/bin/env python3
# Run 11: per fire -> did the landing problem happen (next slot? dump late in its block? Jito turn start?) and COUNTERFACTUAL: replay our buy
# landing at 20 / 35 / 50 ms block-time after the dump (curve state from the run's tape + block sizes), same guard (min_out), same exit
# (hold slots of the run, SL), fees 1.25%/side + tx/tips. Compare with what really happened.
import json, os, time, urllib.request, statistics, sys
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
def rpc(m, p):
    for i in range(6):
        try:
            r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(), headers={"content-type":"application/json"}), timeout=90))
            if "result" in r: return r["result"]
        except Exception: pass
        time.sleep(1.5 * (i + 1))
BC = {}
def blk(s):
    if s not in BC:
        b = rpc("getBlock", [s, {"encoding": "json", "transactionDetails": "signatures", "maxSupportedTransactionVersion": 1, "rewards": False}]); BC[s] = b["signatures"] if b else None
    return BC[s]
es = rpc("getEpochSchedule", []); LS = {}
def leader(s):
    ep = (s - es["firstNormalSlot"]) // es["slotsPerEpoch"]; first = es["firstNormalSlot"] + ep * es["slotsPerEpoch"]
    if first not in LS: LS[first] = {first + i: k for k, v in (rpc("getLeaderSchedule", [s]) or {}).items() for i in v}
    return LS[first].get(s)
FEE = 0.0125
for fn, hold, sl in (("dip_r11.jsonl", 19, 0.20), ("dip_ams_r11.jsonl", 6, 0.10)):
    fire = {}; tape = {}; close = {}; tim = {}; dumps = {}
    for l in open(fn):
        try: r = json.loads(l)
        except Exception: continue
        e = r.get("ev")
        if e == "fire": fire[r["dump_sig"]] = r
        elif e == "tape": tape.setdefault(r["mint"], []).append(r)
        elif e == "close": close[r["dump_sig"]] = r
        elif e == "timing" and r.get("kind") == "fire": tim[r["buy_sig"]] = r
        elif e == "dump": dumps[r["sig"]] = r
    print(f"\n######## {fn} (exit after {hold} slots or SL -{sl:.0%})")
    for ds, f in fire.items():
        c = close.get(ds, {}); td = rpc("getTransaction", [ds, {"encoding": "json", "maxSupportedTransactionVersion": 1}])
        if not td: continue
        S = td["slot"]; bd = blk(S); di = bd.index(ds); N = len(bd); pos = di / N
        landed = (tim.get(f["buy_sig"], {}) or {}).get("buy_sig_seen") or c.get("buy_sig")
        to = rpc("getTransaction", [landed, {"encoding": "json", "maxSupportedTransactionVersion": 1}]) if landed else None
        our_ms = None
        if to:
            bo = blk(to["slot"]); our_ms = (to["slot"] - S) * 212 + (bo.index(landed) / len(bo) - pos) * 212 if bo and landed in bo else None
        L0 = leader(S); turn_start = leader(S - 1) != L0
        tr = sorted([x for x in tape.get(f["mint"], []) if (x["slot"], x["idx"]) > (S, di)], key=lambda x: (x["slot"], x["idx"]))
        for x in tr:
            b = blk(x["slot"]); x["bms"] = (x["slot"] - S) * 212 + ((x["idx"] / len(b)) - pos) * 212 if b else 1e9
        dump_state = (dumps.get(ds, {}).get("vsol") or c.get("dump_vsol"), dumps.get(ds, {}).get("vtok") or c.get("dump_vtok"))
        def sim(X):
            prev = [x for x in tr if x["bms"] <= X]
            V, T = (prev[-1]["vsol"], prev[-1]["vtok"]) if prev else dump_state
            if not V: return None
            Xn = f["spend"] / (1 + FEE); q = T * Xn / (V + Xn)
            if q < f["min_out"]: return ("guard-revert", -0.0005)
            V, T = V + Xn, T - q; s_exit = S + hold
            for x in tr:
                if x["bms"] <= X: continue
                if x["slot"] >= s_exit: break
                if x["buy"]: Tn = V * T / (V + x["sol"]); V, T = V + x["sol"], Tn
                else: Vn = V * T / (T + x["tok"]); V, T = Vn, T + x["tok"]
                val = V * q / (T + q) * (1 - FEE)
                if val <= f["spend"] * (1 - sl): s_exit = x["slot"] + 1
            val = V * q / (T + q) * (1 - FEE)
            return ("filled", (val - f["spend"]) / 1e9 - 0.003)
        real = c.get("result"); rp = ((c.get("curve_pnl") or 0) - (c.get("tips") or 0)) / 1e9 if real == "sold" else -0.0005
        print(f"  {f['mint'][:6]} {f.get('client'):18s} dump at {pos:4.0%} of its block | first slot of leader turn: {'Y' if turn_start else 'n'} | "
              f"we landed {our_ms if our_ms is not None else float('nan'):6.1f} ms block-time ({'NEXT slot' if to and to['slot'] > S else 'same slot'}) -> REAL: {real} {rp:+.4f}")
        for X in (20, 35, 50):
            r = sim(X); print(f"        if we had landed at {X:2d} ms: {r[0] if r else '?':13s} {r[1] if r else 0:+.4f} SOL")
