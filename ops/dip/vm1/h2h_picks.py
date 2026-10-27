#!/usr/bin/env python3
"""VM1 independent check, step 7: M2 (gate cut as live) and IMIT1 picks on the hours where ALL three models are unseen.
  U4 (10-25, after VM1's freeze): the live engines' own "dump" records (FRA r14-r16, AMS r13-r17): M2 pick = m2_pick and
      launch_ok (the gate decision), IMIT1 pick = imit_pass. Coverage = the runs' time spans.
  U3 (10-24 day): the dipdetect study rows of R3 (M2 = model_v3_reg4_top25 predictions >= 0.010095 inside today's
      envelope, i.e. Stage A = the live gate; IMIT1 = f1 >= 0.21089 inside the envelope), mapped to my dumps by
      (mint, slot, tx index). Coverage = R3's window (ends 10-24 16:27 PKT).
Writes /home/moiz/sniper-data/vm1/h2h_picks.npz with per-dump flags aligned to dumps.npz (m2, imit, cov_m2imit)."""
import json, glob, re, os, sys, hashlib
import numpy as np
import core

def sigh(sig):
    return int.from_bytes(hashlib.blake2b(sig.encode(), digest_size=8).digest(), "little")

if __name__ == "__main__":
    D = core.Data(); z = np.load(core.D + "/dumps.npz")
    kd = z["k"]; n = len(kd)
    m2 = np.zeros(n, bool); im = np.zeros(n, bool); cov = np.zeros(n, bool); src = np.zeros(n, np.int8)
    # ---- U4: engine dump records
    key_sig = D.T["sigh"][kd]; order = np.argsort(key_sig); ks = key_sig[order]
    spans = []; nrec = 0; nmatch = 0; seen = set()
    files = [(f, int(re.search(r"_r(\d+)\.jsonl", f).group(1))) for f in glob.glob("/home/moiz/sniper-data/runs/fra/runs/dip_r*.jsonl")]
    files = [(f, r) for f, r in files if r >= 14] + [(f, int(re.search(r"_r(\d+)\.jsonl", f).group(1))) for f in glob.glob("/home/moiz/sniper-data/runs/ams/runs/dip_ams_r*.jsonl")
                                                   if int(re.search(r"_r(\d+)\.jsonl", f).group(1)) >= 13]
    for fn, r in sorted(files):
        smin, smax = None, None
        for line in open(fn):
            if '"ev":"dump"' not in line and '"ev": "dump"' not in line: continue
            try: d = json.loads(line)
            except Exception: continue
            if d.get("ev") != "dump" or "m2" not in d or d.get("sig") in seen: continue
            seen.add(d["sig"]); nrec += 1
            s = d.get("slot"); smin = s if smin is None else min(smin, s); smax = s if smax is None else max(smax, s)
            h = np.uint64(sigh(d["sig"])); q = np.searchsorted(ks, h)
            if q < len(ks) and ks[q] == h:
                j = order[q]; nmatch += 1
                m2[j] = bool(d.get("m2_pick")) and bool(d.get("launch_ok")); im[j] = bool(d.get("imit_pass")); src[j] = 1
        if smin is not None: spans.append((smin, smax))
    for a, b in spans: cov |= (z["slot"] >= a) & (z["slot"] <= b) & (z["lab"] == "U4")
    print(f"U4 engine dump records {nrec}, matched to my dumps {nmatch}; spans {len(spans)}")
    # ---- U3: dipdetect R3 rows
    sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect")
    import dd_lib as L
    DAYS = ("R2", "R3", "R1", "R4")
    lens = {d: len(L.load(d)["k"]) for d in DAYS}
    P = np.load(f"{L.OUT}/pred_v3_reg4_top25.npy"); off = 0
    for d in DAYS:
        if d == "R3": PR3 = P[off: off + lens[d]]
        off += lens[d]
    assert off == len(P)
    d3 = L.load("R3")
    day = np.load("/home/moiz/sniper-data/strategies/patterns/day_R3.npz")
    meta = json.load(open("/home/moiz/sniper-data/strategies/patterns/day_R3_meta.json"))
    meta = meta["meta"] if isinstance(meta, dict) and "meta" in meta else meta
    mints = [x["m"] for x in meta]
    mid = {m: q for q, m in enumerate(D.mints)}
    k3 = d3["k"]; s3 = day["s"][k3]; i3 = day["i"][k3]; t3 = day["tok"][k3]
    gm = np.array([mid.get(mints[t], -1) for t in t3])
    ok = gm >= 0
    g3 = core.pack(np.where(ok, gm, 0), s3, i3, 0)
    gd = core.pack(z["mint"], z["slot"], z["idx"], 0)
    od = np.argsort(gd); gds = gd[od]
    q = np.searchsorted(gds, g3); hit = ok & (q < len(gds)) & (gds[np.minimum(q, len(gds) - 1)] == g3)
    j3 = od[q[hit]]
    m2_3 = (d3["env"] & (PR3 >= 0.010095))[hit]; im_3 = (d3["env"] & np.isfinite(d3["f1"]) & (d3["f1"] >= L.THR["top4"]))[hit]
    sel_u3 = z["lab"][j3] == "U3"
    m2[j3[sel_u3]] |= m2_3[sel_u3]; im[j3[sel_u3]] |= im_3[sel_u3]; src[j3[sel_u3]] = 2
    a, b = L.WIN["R3"]; t_end = L.pk(b)
    s_end = int(np.max(day["s"][k3][d3["t"] < t_end]))
    cov |= (z["lab"] == "U3") & (z["slot"] <= s_end)
    print(f"R3 rows {len(k3)} | mapped to my dumps {hit.sum()} | in U3 {sel_u3.sum()} | M2 picks in U3 {m2_3[sel_u3].sum()} IMIT1 {im_3[sel_u3].sum()} | R3 ends slot {s_end}")
    np.savez(core.D + "/h2h_picks.npz", m2=m2, imit=im, cov=cov, src=src)
    for L_ in ("U3", "U4"):
        mm = (z["lab"] == L_) & cov
        print(L_, "covered dumps", mm.sum(), "M2 picks", (m2 & mm).sum(), "IMIT1 picks", (im & mm).sum(), "VM1 picks", ((z["sm"] >= core.Model().cut) & mm).sum())
