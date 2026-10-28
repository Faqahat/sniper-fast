#!/usr/bin/env python3
"""LIM step 18 (read-only): analyst H's f9 claim checked at OUR MEASURED landed positions.
Buckets = the ideal value of the dump (a buy right after the dump row, wave exit, fol 1.0, gross, mSOL; H's f9 edges).
Pre-send: per window, its FIRST crossing dump; live-filled share; for windows that did NOT fill live: our first try that landed after
that crossing - its need (price vs our limit), slots / outside rows after the dump, and the value of filling it (wave and 2-slot
timer, gross and net of NOW / S2 fill costs), with no limit / +10% / +5%; plus the oracle (bot 247/248) share.
Regular: same per fire (the dump = the trigger; our first landed copy).
Out: data/lim/l18.txt"""
import pickle, sys
import numpy as np
OUT = "/home/moiz/sniper-data/haqq_dissect/lim"
ED = [(-1e9, -10), (-10, 0), (0, 10), (10, 30), (30, 60), (60, 1e9)]
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)


def main():
    E = [e for e in pickle.load(open(f"{OUT}/sel_events.pkl", "rb")) if not e["mayhem"]]
    for kind, cf, cs2 in (("ps", 2.01, 0.49), ("reg", 3.52, 2.03)):
        rows = []
        for e in E:
            if e["kind"] != kind: continue
            if kind == "ps":
                fc = next((c for c in e["cands"] if c["crossed"]), None)
                if fc is None: continue
                d0 = (fc["dump"]["d_slot"], fc["dump"]["d_idx"])
                same = [c for c in e["cands"] if c["crossed"] and (c["dump"]["d_slot"], c["dump"]["d_idx"]) == d0]
                first = same[0]
                rows.append(dict(day=e["day"], ideal=1000 * fc["ideal"][("wv", 1.0)], live=e["live_fill"], c=first, oracle=fc["dump"]["oracle"],
                                 live_val=next((1000 * c["val"][("wv", 1.0)] for c in e["cands"] if c["ok"]), None)))
            else:
                c = e["cands"][0]
                rows.append(dict(day=e["day"], ideal=1000 * c["ideal"][("wv", 1.0)], live=e["live_fill"], c=c, oracle=c["dump"]["oracle"],
                                 live_val=1000 * c["val"][("wv", 1.0)] if e["live_fill"] else None))
        P(f"\n## {kind}: {len(rows)} {'windows with a crossing' if kind == 'ps' else 'fires'} - by the dump's ideal value (buy right after the dump, wave, gross mSOL)")
        P("| ideal value | n | live fill share | oracle share | live fills: value at our position (wave, gross) | NOT filled live: n | their first try: need p50 / slots after dump 0-1-2+ % / rows ahead p50 | fill it, no limit: wave gross / 2-slot gross / wave net NOW / net S2 (mSOL per fill) | +10%: fills, wave net NOW | +5%: fills, wave net NOW | value lost vs ideal (wave, mSOL) |")
        P("|---|---|---|---|---|---|---|---|---|---|---|")
        for lo, hi in ED:
            v = [r for r in rows if lo <= r["ideal"] < hi]
            if not v: continue
            lf = [r["live_val"] for r in v if r["live"] and r["live_val"] is not None]
            nf = [r for r in v if not r["live"]]
            if nf:
                need = np.median([r["c"]["need"] for r in nf]); ds = np.array([r["c"]["dslots"] for r in nf])
                wg = np.mean([1000 * r["c"]["val"][("wv", 1.0)] for r in nf]); tg = np.mean([1000 * r["c"]["val"][("tm", 1.0)] for r in nf])
                f10 = [r for r in nf if r["c"]["need"] <= 1.10]; f5 = [r for r in nf if r["c"]["need"] <= 1.05]
                lost = np.mean([1000 * (r["c"]["ideal"][("wv", 1.0)] - r["c"]["val"][("wv", 1.0)]) for r in nf if r["c"].get("ideal")])
                P(f"| {lo:g}..{hi:g} | {len(v)} | {np.mean([r['live'] for r in v]):.3f} | {np.mean([r['oracle'] for r in v]):.2f} | {np.mean(lf) if lf else float('nan'):+.1f} (n {len(lf)}) | {len(nf)} | "
                  f"{need:.3f} / {100*np.mean(ds==0):.0f}-{100*np.mean(ds==1):.0f}-{100*np.mean(ds>=2):.0f} / {np.median([r['c']['nahead'] for r in nf]):.0f} | "
                  f"{wg:+.1f} / {tg:+.1f} / {wg - cf:+.1f} / {wg - cs2:+.1f} | {len(f10)}, {np.mean([1000*r['c']['val'][('wv',1.0)] - cf for r in f10]) if f10 else float('nan'):+.1f} | "
                  f"{len(f5)}, {np.mean([1000*r['c']['val'][('wv',1.0)] - cf for r in f5]) if f5 else float('nan'):+.1f} | {lost:+.1f} |")
        # oracle-only view of the not-filled
        nf = [r for r in rows if not r["live"]]
        for nm, sel in (("oracle dumps", lambda r: r["oracle"]), ("non-oracle dumps", lambda r: not r["oracle"])):
            w = [r for r in nf if sel(r)]
            if not w: continue
            for dsn, dsl in (("same slot as dump", lambda r: r["c"]["dslots"] == 0), ("next slot", lambda r: r["c"]["dslots"] == 1), ("2+ slots", lambda r: r["c"]["dslots"] >= 2)):
                x = [r for r in w if dsl(r)]
                if not x: continue
                P(f"- not filled live, {nm}, our try landed {dsn}: n {len(x)}, need p50 {np.median([r['c']['need'] for r in x]):.3f}, fill with no limit: wave gross {np.mean([1000*r['c']['val'][('wv',1.0)] for r in x]):+.1f} mSOL, "
                  f"net NOW {np.mean([1000*r['c']['val'][('wv',1.0)] - cf for r in x]):+.1f}, fol 0.9 net {np.mean([1000*r['c']['val'][('wv',0.9)] - cf for r in x]):+.1f}; ideal at the dump {np.mean([1000*r['c']['ideal'][('wv',1.0)] for r in x]):+.1f}")
    open(f"{OUT}/l18.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
