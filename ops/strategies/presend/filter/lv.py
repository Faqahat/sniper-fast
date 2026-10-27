#!/usr/bin/env python3
"""PRESEND FILTER: the live pre-send records of one run -> one row per ARMED window (MEASURED, the engine's own records).
Every window: trigger, arm time, its attempts (send time / slot, landed result, fee), the disarm, and when it filled: the fill, exit,
sell, realized P&L (engine), token-account rent back (dip19 runs: presend_live_ata_close; older runs closed it in the sell, so the
rent is already inside realized). Window / attempt ids restart at each engine start: keys carry the segment.
HOLDOUT GUARD: refuses any file name with r26."""
import json, collections, re, os

LIVE = "/home/moiz/sniper-data/presend_filter/live"
WALLET = {"ams": "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "fra": "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
RUNFILES = {"ams:r19": "dip_ams_r19", "ams:r20": "dip_ams_r20", "ams:r24": "dip_ams_r24", "ams:r25": "dip_ams_r25",
            "fra:r21": "fra_dip_r21", "fra:r22": "fra_dip_r22", "fra:r23": "fra_dip_r23", "fra:r24": "fra_dip_r24"}
DEV = ("ams:r24", "ams:r25")
VAL = ("fra:r23", "fra:r24", "ams:r19", "ams:r20", "fra:r21", "fra:r22")


def path_of(run, base=LIVE):
    fn = f"{base}/{RUNFILES[run]}.jsonl" if run in RUNFILES else run
    if re.search(r"r26", os.path.basename(fn)) and not os.environ.get("PSF_ALLOW_HOLDOUT"):
        raise SystemExit("HOLDOUT GUARD: r26 files are not read by the research code (apply_filter.py is the owner's tool)")
    return fn


def load(run, fn=None):
    fn = fn or path_of(run)
    seg = 0
    W = collections.OrderedDict(); att = {}; land = {}; skips = []; ata = []; segs = []; sh_arm = {}; sh_fill = []; sh_exit = []
    for line in open(fn):
        if '"ev":"presend' not in line and '"ev":"run_start"' not in line: continue
        try: r = json.loads(line)
        except Exception: continue
        ev = r.get("ev")
        if ev == "run_start":
            seg += 1
            segs.append(dict(seg=seg, t=r["t"], cfg=r.get("presend_live"), sh=r.get("presend"), wallet=r.get("wallet")))
            continue
        r["seg"] = seg
        if ev == "presend_live_arm":
            W[(seg, r["w"])] = dict(seg=seg, w=r["w"], arm=r, disarm=None, fills=[], exits=[], sells=[], close=None, realized=None, atts=[])
        elif ev == "presend_live_disarm":
            if (seg, r["w"]) in W: W[(seg, r["w"])]["disarm"] = r
        elif ev == "presend_live_skip": skips.append(r)
        elif ev == "presend_attempt":
            att[r["sig"]] = r
            if (seg, r["w"]) in W: W[(seg, r["w"])]["atts"].append(r["sig"])
        elif ev == "presend_attempt_land": land[r["sig"]] = r
        elif ev == "presend_live_fill":
            if (seg, r["w"]) in W: W[(seg, r["w"])]["fills"].append(r)
        elif ev == "presend_live_exit":
            if (seg, r["w"]) in W: W[(seg, r["w"])]["exits"].append(r)
        elif ev == "presend_live_sell_land":
            if (seg, r["w"]) in W: W[(seg, r["w"])]["sells"].append(r)
        elif ev == "presend_live_close":
            if (seg, r["w"]) in W: W[(seg, r["w"])]["close"] = r
        elif ev == "presend_live_realized":
            if (seg, r["w"]) in W: W[(seg, r["w"])]["realized"] = r
        elif ev == "presend_live_ata_close": ata.append(r)
        elif ev == "presend_arm": sh_arm[(seg, r["w"])] = r
        elif ev == "presend_fill": sh_fill.append(r)
        elif ev == "presend_exit": sh_exit.append(r)
    return dict(run=run, segs=segs, W=W, att=att, land=land, skips=skips, ata=ata, sh_arm=sh_arm, sh_fill=sh_fill, sh_exit=sh_exit)


def windows(R, our_failed=None):
    """one dict per armed window. our_failed: sig -> chain fee of OUR failed txs (raw recording), for tries the engine logged as unseen.
    fail_fee = fees of this window's attempts that landed and failed (MEASURED: land record, else the chain)."""
    out = []
    used_ata = set()
    for (seg, w), X in R["W"].items():
        a = X["arm"]; tr = a["trig"]
        ff = 0; nf = 0; n_unseen_landed = 0; n_ok = 0
        for sig in X["atts"]:
            L = R["land"].get(sig) or {}
            res = L.get("res")
            if res == "ok": n_ok += 1; continue
            if res not in (None, "unseen"):
                ff += L.get("fee") if L.get("fee") is not None else 5120; nf += 1
            elif our_failed is not None and sig in our_failed:
                ff += our_failed[sig]; nf += 1; n_unseen_landed += 1
        row = dict(run=R["run"], seg=seg, w=w, mint=tr["mint"], trig=tr, arm_t=a.get("t") or tr["t"], en_slot=a["en_slot"], spend=a.get("spend"), lim0=a.get("lim0"),
                   n_att=len(X["atts"]), fail_fee=ff, n_fail=nf, n_unseen_landed=n_unseen_landed, disarm=X["disarm"], filled=bool(X["fills"]))
        if X["fills"]:
            f = X["fills"][0]; rz = X["realized"] or {}; cl = X["close"] or {}
            ac = None
            for k, z in enumerate(R["ata"]):
                if k in used_ata: continue
                if z["seg"] == seg and z["mint"] == tr["mint"] and z.get("slot", 0) >= f["slot"]:
                    ac = z; used_ata.add(k); break
            rent_back = (ac or {}).get("delta") or 0
            row.update(fill=f, n_fills=len(X["fills"]), exit=(X["exits"] or [None])[0], sells=X["sells"], close=cl, realized=rz.get("pnl"), rent_back=rent_back,
                       ata_close_fee=(ac or {}).get("fee"), net=(rz.get("pnl") or 0) + rent_back, fill_sig=f["sig"], fill_slot=f["slot"], fill_idx=f["idx"], fill_t=f["t"],
                       fill_att=R["att"].get(f["sig"]))
        out.append(row)
    return out


if __name__ == "__main__":
    import sys
    for run in (sys.argv[1:] or list(RUNFILES)):
        R = load(run); Ws = windows(R)
        F = [x for x in Ws if x["filled"]]
        print(run, "segs", len(R["segs"]), "windows", len(Ws), "filled", len(F), "realized %+.4f" % (sum(x["realized"] or 0 for x in F) / 1e9),
              "rent back %+.4f" % (sum(x["rent_back"] for x in F) / 1e9), "fail fee (land records only) %.4f" % (sum(x["fail_fee"] for x in Ws) / 1e9),
              "multi-fill", sum(1 for x in F if x["n_fills"] > 1), "no realized", sum(1 for x in F if x["realized"] is None))
