#!/usr/bin/env python3
# H2H step 1 (read-only, local): every live fire of ours (FRA 2g7rYv7y runs 9-14, AMS EgxfYgEb runs 9-14) matched to the recording:
# our landed tx (fill = trade event, fail = failed tx with its error code, none = no copy landed), its block-position delay after the
# dump (same clock as haqq's: slot x 212 ms + index / block size x 212 ms), the price at our landing vs the post-dump price, the outside
# buyers that landed between the dump and us (haqq, fast cohort bots, others), and haqq's response to the SAME dump (its buy / failed
# attempt within 400 ms and before the next outside sell >= 1 SOL; delay, order vs ours, price ratio, its lot P&L with its real exit).
# Output: sniper-data/haqq/h2h_fires.json
import sys, json, glob, pickle, zlib, collections, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/haqq"); import h_lib as H
SS = {}
for run in ("R1", "R2", "R3", "R4"):
    for k, v in json.load(open(f"{H.OUT}/slotmax_{run}.json")).items(): SS[int(k)] = max(SS.get(int(k), 0), v + 1)
def A(s, i): return s * H.SMS + i / max(SS.get(int(s), 400), int(i) + 1) * H.SMS
WAL = {"FRA": "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "AMS": "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
COH = set(json.load(open("/home/moiz/sniper/ops/overnight/sel/cohort_train.json")))
DYX = "DYXDDrZCLZVeak72eoPg7DgjYz1sW7tMaLY8PusDymQw"
lots = json.load(open(f"{H.OUT}/lots.json"))
LOTIX = {(l["m"], l["buy"]["s"], l["buy"]["i"]): li for li, l in enumerate(lots)}
fires = []
for srv, pat in (("FRA", "/home/moiz/sniper-data/runs/fra/runs/dip_r{}.jsonl"), ("AMS", "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r{}.jsonl")):
    for run in range(9, 15):
        f = pat.format(run)
        try: fh = open(f)
        except FileNotFoundError: continue
        F_ = {}; C_ = {}; BL = {}; BF = {}; T_ = {}
        for l in fh:
            try: r = json.loads(l)
            except Exception: continue
            e = r.get("ev")
            if e == "fire": F_[r["buy_sig"]] = r
            elif e == "close": C_[r["buy_sig"]] = r
            elif e == "buy_land": BL[r["sig"]] = r
            elif e == "buy_failed": BF[r["sig"]] = r
            elif e == "timing": T_[r.get("buy_sig")] = r
        for bs, fr in F_.items():
            sigs = {bs}
            nn = fr.get("nonce") or {}
            for x in nn.get("per_path") or []: sigs.add(x["sig"])
            for x in nn.get("variants") or []: sigs.add(x["sig"])
            for x in fr.get("variants") or []: sigs.add(x["sig"])
            c = C_.get(bs) or next((x for x in C_.values() if x.get("dump_sig") == fr["dump_sig"]), None)
            fires.append(dict(srv=srv, run=run, mint=fr["mint"], dump_sig=fr["dump_sig"], slot=fr.get("slot"), client=fr.get("client"), t_fire=fr.get("t_fire") or fr.get("t"),
                              spend=fr.get("spend"), tips_cfg=fr.get("tips"), sigs=sorted(sigs), close=c, timing=T_.get(bs)))
print("fires", len(fires), collections.Counter((f["srv"], f["run"]) for f in fires))
by = collections.defaultdict(list)
for f in fires: by[zlib.crc32(f["mint"].encode()) % 64].append(f)
out = []; miss = collections.Counter()
for b, fs in by.items():
    tp = pickle.load(open(f"{H.OUT}/tp/b{b:02d}.pkl", "rb"))
    for f in fs:
        d = tp.get(f["mint"])
        if d is None: miss["no tape"] += 1; out.append(dict(f, status="no tape")); continue
        T = d["T"]; Wl = d["W"]; users = [Wl[x] for x in T[:, 5]]; s16 = d["sig"]; F = d["F"]; fs16 = d["fsig"]
        kd = next((j for j, x in enumerate(s16) if x == f["dump_sig"][:16]), None)
        if kd is None and f["close"] and f["close"].get("dump_slot") is not None:
            kd = next((j for j in range(len(T)) if T[j, 0] == f["close"]["dump_slot"] and T[j, 1] == f["close"].get("dump_idx")), None)
        if kd is None: miss["dump not on tape"] += 1; out.append(dict(f, status="no dump")); continue
        wal = WAL[f["srv"]]; mysig = {x[:16] for x in f["sigs"]}
        a_d = A(T[kd, 0], T[kd, 1]); p_post = T[kd, 9] / T[kd, 10]
        rec = dict(f, dump_s=int(T[kd, 0]), dump_i=int(T[kd, 1]), dump_sol=float(T[kd, 7]) / 1e9, a_dump=a_d, t_pkt=H.pkt(T[kd, 3]) if T[kd, 3] else None, bt=int(T[kd, 3]))
        rec.pop("close", None); rec.pop("timing", None)
        ko = next((j for j in range(kd + 1, len(T)) if s16[j] in mysig and users[j] == wal and T[j, 6]), None)
        fo = next((j for j in range(len(F)) if fs16[j] in mysig), None)
        if ko is not None:
            st = "fill"; s_, i_ = int(T[ko, 0]), int(T[ko, 1])
            Vp = T[ko, 9] - T[ko, 7]; Tp = T[ko, 10] + T[ko, 8]; p_land = Vp / Tp
            # our P&L from the chain: buy cost, then our next sell(s) of this mint (until tokens are gone)
            cost = float(T[ko, 7] + T[ko, 11] + T[ko, 12] + T[ko, 15] + T[ko, 19]) / 1e9; got = 0.0; tok = float(T[ko, 8]); ks = None; sell_tx = 0.0
            for j in range(ko + 1, len(T)):
                if users[j] == wal and not T[j, 6]:
                    got += float(T[j, 7] - T[j, 11] - T[j, 12] - T[j, 15] - T[j, 19]) / 1e9; sell_tx += float(T[j, 15] + T[j, 19]) / 1e9
                    tok -= float(T[j, 8]); ks = j if ks is None else ks
                    if tok <= 1: break
            rec.update(our_cost=cost, our_got=got, our_pnl=got - cost if ks is not None else None, our_buy_tx=float(T[ko, 15] + T[ko, 19]) / 1e9, our_sell_tx=sell_tx,
                       our_exit_s=int(T[ks, 0]) if ks is not None else None, our_tok=float(T[ko, 8]), our_sol=float(T[ko, 7]) / 1e9)
        elif fo is not None:
            st = "fail"; s_, i_ = int(F[fo, 0]), int(F[fo, 1]); rec.update(fail_code=int(F[fo, 5]), fail_fee=float(F[fo, 6]) / 1e9)
            j = int(np.searchsorted(T[:, 0] * 100000 + T[:, 1], s_ * 100000 + i_)) - 1
            p_land = T[j, 9] / T[j, 10] if j >= 0 else p_post
        else:
            st = "none"; s_ = i_ = None; p_land = None
        rec["status"] = st
        if s_ is not None:
            a_o = A(s_, i_); rec.update(our_s=s_, our_i=i_, our_delay=a_o - a_d, our_same=s_ == T[kd, 0], our_pratio=float(p_land / p_post))
            # outside buyers that landed between the dump and us
            ahead = [j for j in range(kd + 1, len(T)) if (T[j, 0], T[j, 1]) < (s_, i_) and T[j, 6] and users[j] != wal]
            def who(u):
                if u == H.W: return "haqq"
                if u == H.HK: return "hk"
                if u == DYX: return "dyx"
                if u in COH: return "cohort"
                return "other"
            rec["ahead"] = [(who(users[j]), float(T[j, 7]) / 1e9, A(T[j, 0], T[j, 1]) - a_d) for j in ahead]
        # haqq's response to this dump
        j_end = next((j for j in range(kd + 1, len(T)) if not T[j, 6] and T[j, 7] >= 1e9 and users[j] != H.W), len(T))
        hb = [j for j in range(kd + 1, j_end) if users[j] == H.W and T[j, 6] and A(T[j, 0], T[j, 1]) - a_d <= 400]
        hf = []
        for j in range(len(F)):
            if Wl[F[j, 3]] != H.W or F[j, 4] != 0: continue
            a_ = A(F[j, 0], F[j, 1])
            if 0 < a_ - a_d <= 400 and (j_end >= len(T) or (F[j, 0], F[j, 1]) < (T[j_end, 0], T[j_end, 1])): hf.append(j)
        rec["haqq_fail_n"] = len(hf)
        if hb:
            j = hb[0]; li = LOTIX.get((f["mint"], int(T[j, 0]), int(T[j, 1])))
            Vp = T[j, 9] - T[j, 7]; Tp = T[j, 10] + T[j, 8]
            rec.update(haqq="fill", h_s=int(T[j, 0]), h_i=int(T[j, 1]), h_delay=A(T[j, 0], T[j, 1]) - a_d, h_sol=float(T[j, 7]) / 1e9, h_pratio=float((Vp / Tp) / p_post), h_nbuys=len(hb), h_li=li,
                       h_pnl=(lots[li]["got"] - lots[li]["cost"]) if li is not None and lots[li]["closed"] else None, h_cost=lots[li]["cost"] if li is not None else None,
                       h_exit_s=lots[li]["sells"][0]["s"] if li is not None and lots[li]["sells"] else None,
                       h_pnl_all=sum((lots[LOTIX[(f["mint"], int(T[x, 0]), int(T[x, 1]))]]["got"] - lots[LOTIX[(f["mint"], int(T[x, 0]), int(T[x, 1]))]]["cost"]) for x in hb if LOTIX.get((f["mint"], int(T[x, 0]), int(T[x, 1]))) is not None))
            if s_ is not None: rec["h_first"] = (int(T[j, 0]), int(T[j, 1])) < (s_, i_)
        elif hf:
            rec.update(haqq="fail", h_delay=A(F[hf[0], 0], F[hf[0], 1]) - a_d)
        else: rec["haqq"] = "none"
        out.append(rec)
json.dump(out, open(f"{H.OUT}/h2h_fires.json", "w"), default=lambda o: o.item() if hasattr(o, "item") else str(o))
print("missing:", dict(miss)); c = collections.Counter((r["srv"], r["status"]) for r in out); print(sorted(c.items()))
print("haqq on our fired dumps:", collections.Counter((r["status"], r.get("haqq")) for r in out))
