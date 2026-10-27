import sys, os, re, glob, json
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filter")
import apply_filter as af
fn = "/home/moiz/sniper-data/presend_filter/live/fetched/ams_dip_ams_r26.jsonl"
cohort = set(json.load(open(af.COHORT))); fbots = set(json.load(open(af.FBOTS)))
recs = [d for d in sorted(glob.glob(f"{af.COLLECT}/run_*")) if os.path.isdir(f"{d}/txs")]
tmin = tmax = None
for line in open(fn):
    m = re.search(r'"t":(\d{19})', line)
    if m:
        t = int(m.group(1)) / 1e9
        tmin = t if tmin is None else min(tmin, t); tmax = t if tmax is None else max(tmax, t)
rows, fails = af.load_chain((int(tmin - af.HIST_H * 3600), int(tmax + 600)), recs, 12)
C = af.ChainIx(rows); af.G["C"] = C
Ws = af.windows("ams:r26", fn, C, fails, cohort, fbots)
tot, rem = af.evaluate(Ws, "quiet")
print("TOTAL", f"{tot['before']:+.4f} -> {tot['after']:+.4f}", flush=True)
fee_rate = sum(w["fail_fee"] for w in Ws) / max(sum(len(w["tries"]) for w in Ws), 1)
out = []
for w in Ws:
    v = w["net"] if w["filled"] else 0
    before = (v - w["fail_fee"]) / 1e9
    q = w["q"]
    skip = q is not None and (q["since_last"] >= 1 and q["coh_hold"] == 0 and q["fb_n"] < 2 and q["wh_dump_fol"] < 2.24)
    if skip:
        after = 0.0
    else:
        fee_kept = 0; fill_kept = w["filled"]
        for t in w["tries"]:
            send = True
            if q is not None and t["slot"] >= w["trig"]["slot"] + 6:
                send = af.others_seen(C, w["mint"], q["k_trig"], w["trig"]["wallet"], t["pos"]) >= 2
            if send: fee_kept += t["fee"]
            if t["fill"]: fill_kept = send
        if w["filled"] and not fill_kept:
            fee_kept += max(w["en_slot"] - w["fill_slot"], 0) * w["k"] * fee_rate
        after = ((v if fill_kept else 0) - fee_kept) / 1e9
    out.append(dict(run="ams:r26", t=w["t"], spend=500000000, filled=bool(w["filled"]), before=before, after=after))
json.dump(out, open(sys.argv[1], "w"))
print("per-window sum", f"{sum(o['before'] for o in out):+.4f} -> {sum(o['after'] for o in out):+.4f}", len(out))
