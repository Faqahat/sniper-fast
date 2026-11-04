#!/usr/bin/env python3
"""dip36 SKIP-2 ledger seed builder [read-only on the run logs]: the engine's --presend-skip2-seed FILE = the creator / whale / mint ledgers
of the SKIP-2 per-send score (ENGINE_SPEC_PERSEND.txt inputs 46-55; s2_table.py logic), built from our earlier engine logs in time order,
so the live score starts with the history the model was trained with (spec section 4: ledgers seeded, own results + activity reset).
  cre[creator]  = [realized positions whose arm had this ann.creator, their pnl sum (SOL), arms with this creator]
  wh[whale]     = [realized positions whose arm's whale (T2 trig.wallet / re-arm dump.seller), pnl sum, arms, disarms, filled disarms]
  mint[mint]    = [realized positions on the mint, pnl sum, arms]
usage: s2_seed.py --out /root/dip/skip2_seed.json RUN.jsonl [RUN.jsonl ...]   (oldest first, e.g. dip_ams_r37.jsonl .. the last run)"""
import argparse, collections, json, os, time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("runs", nargs="+")
    a = ap.parse_args()
    cre = collections.defaultdict(lambda: [0, 0.0, 0])
    wh = collections.defaultdict(lambda: [0, 0.0, 0, 0, 0])
    mint_l = collections.defaultdict(lambda: [0, 0.0, 0])
    n = collections.Counter()
    for fn in a.runs:
        armmeta = {}; closes = collections.defaultdict(list); used = collections.Counter()
        for raw in open(fn, "rb"):
            if b'"ev":"presend_live_' not in raw: continue
            if not any(k in raw for k in (b'"presend_live_arm"', b'"presend_live_disarm"', b'"presend_live_close"', b'"presend_live_realized"')): continue
            try: d = json.loads(raw)
            except Exception: continue
            ev = d.get("ev")
            if ev == "presend_live_arm":
                kind = d.get("kind") or "T2"; T2 = kind == "T2"
                tr = (d.get("trig") if T2 else d.get("dump")) or {}
                mint = d.get("mint") or tr.get("mint"); w = d.get("w")
                whale = tr.get("wallet") if T2 else tr.get("seller"); creator = (d.get("ann") or {}).get("creator")
                armmeta[(mint, w)] = (kind, whale, creator)
                wh[whale][2] += 1; mint_l[mint][2] += 1
                if creator: cre[creator][2] += 1
                n["arms"] += 1
            elif ev == "presend_live_disarm":
                m = armmeta.get((d.get("mint"), d.get("w")))
                if m: wh[m[1]][3] += 1; wh[m[1]][4] += 1 if d.get("filled") else 0
            elif ev == "presend_live_close":
                closes[(d["mint"], d["pid"])].append(d)
            elif ev == "presend_live_realized":
                key = (d["mint"], d["pid"]); L = closes.get(key) or []
                c = L[used[key]] if used[key] < len(L) else None; used[key] += 1
                pnl = (d.get("pnl") or 0) / 1e9
                w = d.get("w") if d.get("w") is not None else (c or {}).get("w")
                m = armmeta.get((d["mint"], w))
                mint_l[d["mint"]][0] += 1; mint_l[d["mint"]][1] += pnl
                if m:
                    wh[m[1]][0] += 1; wh[m[1]][1] += pnl
                    if m[2]: cre[m[2]][0] += 1; cre[m[2]][1] += pnl
                n["realized"] += 1
        print(fn, dict(n), flush=True)
    out = {"skip2_seed": 1, "built": time.time(), "runs": [os.path.basename(r) for r in a.runs], "counts": dict(n),
           "cre": cre, "wh": {str(k): v for k, v in wh.items()}, "mint": mint_l}
    tmp = a.out + ".tmp"
    json.dump(out, open(tmp, "w"))
    os.replace(tmp, a.out)
    print(f"wrote {a.out}: {len(cre)} creators, {len(wh)} whales, {len(mint_l)} mints")


if __name__ == "__main__":
    main()
