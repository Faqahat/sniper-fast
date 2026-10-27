#!/usr/bin/env python3
"""QUIET (dip20) PARITY, the replay side: per armed window of a live run, what the research replay (apply_filter.py, the
"quiet" config = C11-24h + C5) decides, written as JSON for the engine-side harness to compare against
(quiet_parity_compare.py). Read-only: local files (apply_filter.get_records may fetch a run's records with `ssh ... sudo cat`).

  python3 quiet_parity_export.py --run ams:r24 --run ams:r25 --out DIR [--live PATH] [--procs N]

Per window (seg, w): the trigger (mint, sig, slot, idx, j, wallet, t), the live window (en_slot, its disarm: why, slot), every
try (slot, pos), and the replay's decision:
  q            the four arm signals (apply_filter.quiet_signals: since_last, coh_hold, fb_n, wh_dump_fol) or null when the trigger
               is not on the chain recording (apply_filter then keeps the window as live)
  skip         all four quiet signals hold (since_last >= 1, coh_hold == 0, fb_n < 2, wh_dump_fol < 2.24)
  stop         C5 (N 6, M 2): the first try at slot >= trigger slot + 6 whose 'other trades seen' (apply_filter.others_seen: the
               token's chain rows after the trigger up to the try's pos, not the whale, not the AMS / FRA wallets) is < 2;
               stop_slot = that try's slot, stop_k = its index, others = its count; others_own = the same count excluding only
               the run's own wallet (what the engine knows); first6_slot / first6_others[_own] = the first try at >= trigger + 6
The span read from the raw recording is apply_filter's (first trigger - 30 h .. last + 600 s)."""
import sys, os, json, re, argparse, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import apply_filter as AF

OWN = {"ams": "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "fra": "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
N_STOP, M_STOP = 6, 2


def others(C, mint, k_trig, whale, pos, excl):
    n = 0
    for k in C.by_mint[mint][k_trig + 1:]:
        x = C.rows[k]
        if (x[0], x[1], x[2]) > tuple(pos): break
        if x[5] != whale and x[5] not in excl: n += 1
    return n


def disarms(fn):
    seg = 0; out = {}
    for line in open(fn):
        if '"ev":"run_start"' in line: seg += 1; continue
        if '"ev":"presend_live_disarm"' not in line: continue
        r = json.loads(line)
        out[(seg, r["w"])] = dict(why=r.get("why"), slot=r.get("slot"), t=r.get("t"), attempts=r.get("attempts"), filled=r.get("filled"))
    return out


def seg_starts(fn):
    seg = 0; out = {}
    for line in open(fn):
        if '"ev":"run_start"' in line:
            seg += 1
            r = json.loads(line)
            out[seg] = r.get("t")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="append", required=True); ap.add_argument("--out", required=True)
    ap.add_argument("--live"); ap.add_argument("--procs", type=int, default=12)
    A = ap.parse_args()
    os.makedirs(A.out, exist_ok=True)
    cohort = set(json.load(open(AF.COHORT))); fbots = set(json.load(open(AF.FBOTS)))
    recs = sorted(d for d in __import__("glob").glob(f"{AF.COLLECT}/run_*") if os.path.isdir(f"{d}/txs"))
    for run in A.run:
        t0 = time.time()
        fn = AF.get_records(run, A.live)
        region = run.split(":")[0]
        tmin = tmax = None
        for line in open(fn):
            m = re.search(r'"t":(\d{19})', line)
            if m:
                t = int(m.group(1)) / 1e9
                tmin = t if tmin is None else min(tmin, t); tmax = t if tmax is None else max(tmax, t)
        span = (int(tmin - AF.HIST_H * 3600), int(tmax + 600))
        rows, fails = AF.load_chain(span, recs, A.procs)
        C = AF.ChainIx(rows); AF.G["C"] = C
        Ws = AF.windows(run, fn, C, fails, cohort, fbots)
        dis = disarms(fn); starts = seg_starts(fn)
        out = []
        for w in Ws:
            q = w["q"]; tr = w["trig"]
            r = dict(seg=w["seg"], w=w["w"], mint=w["mint"], sig=tr["sig"], slot=tr["slot"], idx=tr["idx"], j=tr.get("j", 0), wallet=tr["wallet"], t=tr["t"],
                     arm_t=w["t"], en_slot=w["en_slot"], filled=w["filled"], disarm=dis.get((w["seg"], w["w"])),
                     tries=[[t["slot"], list(t["pos"])] for t in w["tries"]], fill_k=next((k for k, t in enumerate(w["tries"]) if t["fill"]), None))
            if q is None:
                r["replay"] = dict(found=False)
            else:
                skip = q["since_last"] >= 1 and q["coh_hold"] == 0 and q["fb_n"] < 2 and q["wh_dump_fol"] < 2.24
                st = dict(stop=False, stop_slot=None, stop_k=None, others=None, others_own=None, first6_slot=None, first6_others=None, first6_others_own=None)
                for k, t in enumerate(w["tries"]):
                    if t["slot"] < tr["slot"] + N_STOP: continue
                    nb = others(C, w["mint"], q["k_trig"], tr["wallet"], t["pos"], AF.WALLETS)
                    no = others(C, w["mint"], q["k_trig"], tr["wallet"], t["pos"], {OWN[region]})
                    if st["first6_slot"] is None: st.update(first6_slot=t["slot"], first6_others=nb, first6_others_own=no)
                    if nb < M_STOP:
                        st.update(stop=True, stop_slot=t["slot"], stop_k=k, others=nb, others_own=no)
                        break
                r["replay"] = dict(found=True, since_last=q["since_last"], coh_hold=q["coh_hold"], fb_n=q["fb_n"], wh_dump_fol=q["wh_dump_fol"], skip=skip, **st)
            out.append(r)
        path = f"{A.out}/replay_{run.replace(':', '_')}.json"
        json.dump(dict(run=run, records=fn, span=span, recs=recs, seg_starts=starts, own=OWN[region], windows=out), open(path, "w"))
        nf = sum(1 for x in out if not x["replay"]["found"])
        print(f"{run}: {len(out)} windows ({nf} trigger not on the recording), skip {sum(1 for x in out if x['replay'].get('skip'))}, "
              f"stop {sum(1 for x in out if x['replay'].get('stop'))} -> {path} ({time.time() - t0:.0f} s)", flush=True)
        del C, rows, AF.G["C"]


if __name__ == "__main__":
    main()
