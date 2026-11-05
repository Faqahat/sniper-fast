#!/usr/bin/env python3
"""APEX-FEES step 4: what decides create-slot position, per leader client; rival recipes; threshold to be first.
Reads fees/T.pkl (f2_build.py). Prints a plain-text report (tee it to fees/analyze.txt). Labels: [M] measured, [I] inferred."""
import sys, collections, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/apex2/fees")
import fl

CL = ["AgaveBam", "JitoLabs", "HarmonicAgave", "HarmonicFiredancer", "Firedancer", "FireBAM", "Rakurai", "Agave"]
RIV = ["6Z91Dgiz", "dKMjeGJ4", "AHwJSnFN", "8RvtT818", "4yFAz7dp", "2mqrindM", "FiFawHqx", "CWiNFAEk", "4zT7uCnA", "BXB7FF4m"]
ms = lambda x: x / 1e6

def pct(a, q): return np.percentile(a, q) if len(a) else np.full(len(q) if hasattr(q, "__len__") else 1, np.nan)

def main():
    C, L = fl.load(); N = len(C["run"])
    lane1 = np.array([(l.split("+")[0] if l else "none") for l in C["lanes"]], object)
    u8 = np.array([s[:8] for s in C["user"]], object); s8 = np.array([s[:8] for s in C["signer"]], object)
    tot = C["prio"] + C["tips"]
    # ---------- groups: non-bundle landed buys in the create slot, first tx per user, by launch
    B = np.flatnonzero((C["role"] == "buy") & (C["so"] == 0) & (C["rank"] >= 0))
    G = collections.defaultdict(list)
    for k in B: G[C["mint"][k]].append(k)
    for v in G.values(): v.sort(key=lambda k: C["i"][k])
    print(f"[M] rows {N:,}; launches with >=1 non-bundle create-slot buyer {len(G):,}; picks among them "
          f"{sum(1 for m, v in G.items() if C['pick'][v[0]]):,}")

    # ---------- 1. does the top payer come first? (launches with >= 2 non-bundle create-slot buyers)
    print("\n## 1. Is the FIRST non-bundle buyer the TOP payer of its create slot? [M] (groups with >=2 buyers)")
    print("client | groups | buyers p50 | first=max total pay | first=max prio | first=max prio/CU | first=max tip | random 1/n | first paid less than someone later")
    for cl in CL + ["*"]:
        n = 0; a = collections.Counter(); rnd = 0.0; nb = []
        for m, v in G.items():
            if len(v) < 2: continue
            if cl != "*" and C["client"][v[0]] != cl: continue
            n += 1; nb.append(len(v)); rnd += 1 / len(v)
            f = v[0]
            for nm, arr in (("tot", tot), ("prio", C["prio"]), ("cupe", C["cupe"]), ("tips", C["tips"])):
                vals = arr[v]
                if arr[f] >= vals.max(): a[nm] += 1
            if tot[f] < tot[v[1:]].max(): a["less"] += 1
        if n: print(f"{cl} | {n:,} | {np.median(nb):.0f} | {a['tot']/n:.0%} | {a['prio']/n:.0%} | {a['cupe']/n:.0%} | {a['tips']/n:.0%} | {rnd/n:.0%} | {a['less']/n:.0%}")

    # ---------- 2. fixed effects: in-slot order vs log2 prio and log2 tip jointly
    print("\n## 2. Within one create slot: order change per DOUBLING of priority fee vs of tip (joint OLS, launch fixed effects) [M]")
    print("negative = paying more lands earlier. order = rank among non-bundle create-slot buyers.  x = log2(lamports + 10k)")
    print("client | buyers | slope prio | slope tip | slope prio/CU (alt fit) | R2 within")
    for cl in CL + ["*"]:
        Y, X1, X2, X3 = [], [], [], []
        for m, v in G.items():
            if len(v) < 2 or (cl != "*" and C["client"][v[0]] != cl): continue
            r = np.arange(len(v), dtype=float); x1 = np.log2(C["prio"][v] + 1e4); x2 = np.log2(C["tips"][v] + 1e4)
            x3 = np.log2(C["cupe"][v] + 1e3)
            Y.append(r - r.mean()); X1.append(x1 - x1.mean()); X2.append(x2 - x2.mean()); X3.append(x3 - x3.mean())
        if not Y: continue
        y = np.concatenate(Y); X = np.c_[np.concatenate(X1), np.concatenate(X2)]
        b, *_ = np.linalg.lstsq(X, y, rcond=None); r2 = 1 - ((y - X @ b) ** 2).sum() / (y ** 2).sum()
        X_ = np.c_[np.concatenate(X3), np.concatenate(X2)]; b3, *_ = np.linalg.lstsq(X_, y, rcond=None)
        print(f"{cl} | {len(y):,} | {b[0]:+.3f} | {b[1]:+.3f} | {b3[0]:+.3f} | {r2:.2f}")

    # ---------- 3. pairwise: the higher payer is earlier, by pay ratio, per client; split prio-only vs tip-only contrasts
    print("\n## 3. Pairs in the same create slot: P(higher payer lands earlier) by pay ratio [M]")
    print("tot = priority fee + tip. 'prio-only' pairs: both tips < 0.1 mSOL. 'tip-only': priorities within x1.25 of each other (or both < 0.1 mSOL)")
    bins = [(1.0, 1.5), (1.5, 3), (3, 10), (10, 1e9)]
    for kind in ("tot", "prio-only", "tip-only"):
        print(f"- {kind}: client | " + " | ".join(f"x{a:g}-{b:g}" if b < 1e8 else f">x{a:g}" for a, b in bins))
        for cl in CL[:6]:
            cnt = np.zeros((len(bins), 2))
            for m, v in G.items():
                if len(v) < 2 or C["client"][v[0]] != cl: continue
                for x in range(len(v)):
                    for y in range(x + 1, len(v)):
                        a, b_ = v[x], v[y]            # a earlier
                        if kind == "tot": pa, pb = tot[a], tot[b_]
                        elif kind == "prio-only":
                            if C["tips"][a] >= 1e5 or C["tips"][b_] >= 1e5: continue
                            pa, pb = C["prio"][a], C["prio"][b_]
                        else:
                            p1, p2 = C["prio"][a], C["prio"][b_]
                            if not ((p1 < 1e5 and p2 < 1e5) or (min(p1, p2) > 0 and max(p1, p2) / min(p1, p2) <= 1.25)): continue
                            pa, pb = C["tips"][a], C["tips"][b_]
                        hi, lo = max(pa, pb), min(pa, pb)
                        if hi == lo: continue
                        ratio = hi / max(lo, 1e4)
                        for bi, (r0, r1) in enumerate(bins):
                            if r0 <= ratio < r1:
                                cnt[bi, 0] += 1; cnt[bi, 1] += (pa > pb); break
            print(f"  {cl} | " + " | ".join(f"{c1/c0:.0%} (n {int(c0):,})" if c0 else "-" for c0, c1 in cnt))

    # ---------- 3b. Jito-account tips on Jito vs BAM vs others: same-slot pairs with ~0 priority, tip lane jito vs other lane
    print("\n## 3b. Tip LANE matters? pairs in one create slot, both priority < 0.1 mSOL, both tipped [M]")
    print("client | pairs jito-lane tipper vs other-lane tipper | jito-lane earlier | ... when jito tip >= other tip | when jito tip < other tip")
    for cl in CL[:6]:
        n = e = n1 = e1 = n2 = e2 = 0
        for m, v in G.items():
            if len(v) < 2 or C["client"][v[0]] != cl: continue
            for x in range(len(v)):
                for y in range(x + 1, len(v)):
                    a, b_ = v[x], v[y]
                    if C["prio"][a] >= 1e5 or C["prio"][b_] >= 1e5 or C["tips"][a] == 0 or C["tips"][b_] == 0: continue
                    ja, jb = lane1[a] == "jito", lane1[b_] == "jito"
                    if ja == jb: continue
                    j, o = (a, b_) if ja else (b_, a)
                    n += 1; e += ja
                    if C["tips"][j] >= C["tips"][o]: n1 += 1; e1 += ja
                    else: n2 += 1; e2 += ja
        if n: print(f"{cl} | {n:,} | {e/n:.0%} | {e1/max(n1,1):.0%} (n {n1}) | {e2/max(n2,1):.0%} (n {n2})")

    # ---------- 4. the bar to be first, on S2 picks, per client
    for scope, pm in (("S2 picks (all)", C["pick"]), ("all launches", np.ones(N, bool))):
        print(f"\n## 4. {scope}: what the FIRST non-bundle buyer paid, per client [M] (mSOL; tot = priority + tip)")
        print("client | launches w/ buyer | contested (>=2) | first tot p25/50/75/90 | first prio p50 | first tip p50 | first no-tip share | first rel idx p50 | 2nd-place tot p50")
        for cl in CL + ["*"]:
            fs = []; sec = []; con = 0
            for m, v in G.items():
                f = v[0]
                if not pm[f] or (cl != "*" and C["client"][f] != cl): continue
                fs.append(f); con += len(v) >= 2
                if len(v) >= 2: sec.append(tot[v[1]])
            if len(fs) < 20: continue
            fs = np.array(fs); q = pct(ms(tot[fs]), [25, 50, 75, 90])
            print(f"{cl} | {len(fs):,} | {con/len(fs):.0%} | {q[0]:.2f}/{q[1]:.2f}/{q[2]:.2f}/{q[3]:.2f} | {np.median(ms(C['prio'][fs])):.2f} | "
                  f"{np.median(ms(C['tips'][fs])):.2f} | {np.mean(C['tips'][fs]==0):.0%} | {np.median(C['rel'][fs]):.0f} | {np.median(ms(np.array(sec))) if sec else float('nan'):.2f}")
        print(f"P(first | own tot in bin) among non-bundle create-slot buyers, {scope}, contested slots only [M] (association: fast bots also pay more)")
        tb = [0, 0.5, 1, 2, 3, 5, 8, 12, 16, 25, 40, 70, 1e9]
        print("client | " + " | ".join(f"{tb[k]:g}-{tb[k+1]:g}" if tb[k + 1] < 1e8 else f">{tb[k]:g}" for k in range(len(tb) - 1)))
        for cl in CL[:6] + ["*"]:
            n = np.zeros(len(tb) - 1); w = np.zeros(len(tb) - 1)
            for m, v in G.items():
                if len(v) < 2 or not pm[v[0]] or (cl != "*" and C["client"][v[0]] != cl): continue
                for r, k in enumerate(v):
                    bi = np.searchsorted(tb, ms(tot[k]), side="right") - 1
                    n[bi] += 1; w[bi] += (r == 0)
            print(f"{cl} | " + " | ".join(f"{w[k]/n[k]:.0%}({int(n[k])})" if n[k] >= 15 else "-" for k in range(len(n))))

    # ---------- 5. attempts: failures and no-ops around landed buys
    print("\n## 5. Failed / no-op attempts in create slot and +1 (all launches) [M]")
    att = (C["role"] == "fail") | (C["role"] == "noop")
    for cl in CL[:6]:
        mcl = C["client"] == cl
        lb = ((C["role"] == "buy") & mcl).sum()
        print(f"{cl}: landed non-bundle buys {lb:,}; fails {((C['role']=='fail')&mcl).sum():,}; no-ops {((C['role']=='noop')&mcl).sum():,}; "
              f"fail fee p50 {np.median(ms(C['fee'][(C['role']=='fail')&mcl])):.3f} mSOL")
    print("top fail errors:", collections.Counter(C["err"][C["role"] == "fail"]).most_common(8))

    # ---------- 6. rival recipes
    print("\n## 6. Rival recipes (all launches, create slot + next slot) [M]")
    print("wallet | landed buys cs/cs+1 | fails | no-ops | prio p50 mSOL | prio/CU p50 (uLam) | CU limit p50 | CU used p50 | tip p50 mSOL | no-tip % | tips/tx | top lanes | program | cost/landed buy incl. fails mSOL | of which fails | first-rate (cs, all launches) | first-rate by client")
    for w in RIV:
        mw = (u8 == w) | (s8 == w)
        lb = mw & (C["role"] == "buy"); lb0 = lb & (C["so"] == 0)
        fa = mw & (C["role"] == "fail"); no = mw & (C["role"] == "noop")
        cost_all = (C["fee"][mw & (lb | fa | no)].sum() + C["tips"][lb].sum()) / max(lb.sum(), 1)
        cost_f = (C["fee"][fa | no].sum()) / max(lb.sum(), 1)
        k0 = np.flatnonzero(lb0 & (C["rank"] >= 0))
        fr = np.mean(C["rank"][k0] == 0) if len(k0) else np.nan
        byc = []
        for cl in CL[:6]:
            kk = k0[C["client"][k0] == cl]
            if len(kk) >= 15: byc.append(f"{cl[:6]} {np.mean(C['rank'][kk]==0):.0%}")
        cupk = lb0 & (C["cupsrc"] == "cup")
        lanes = collections.Counter(lane1[lb0]).most_common(4)
        prog = collections.Counter(C["xp"][lb0]).most_common(1)[0][0][:8] or "direct pump"
        culv = C["cul"][lb0]; culv = culv[culv > 0]
        print(f"{w} | {lb0.sum()}/{(lb & (C['so']==1)).sum()} | {fa.sum()} | {no.sum()} | {np.median(ms(C['prio'][lb0])):.2f} | "
              f"{np.median(C['cupe'][cupk]) if cupk.sum() else float('nan'):,.0f} | {np.median(culv) if len(culv) else float('nan'):,.0f} | {np.median(C['cu'][lb0]):,.0f} | "
              f"{np.median(ms(C['tips'][lb0])):.2f} | {np.mean(C['tips'][lb0]==0):.0%} | {np.mean(C['ntip'][lb0]):.2f} | "
              f"{', '.join(f'{a} {b}' for a, b in lanes)} | {prog} | {ms(cost_all):.2f} | {ms(cost_f):.2f} | {fr:.0%} | {'; '.join(byc)}")
    # per rival: pay distribution when first vs not first, and when beaten: by whom paying what
    print("\n## 6b. Rivals: their total pay when FIRST vs NOT first (cs, contested slots) [M]")
    for w in RIV:
        k0 = [k for k in np.flatnonzero(((u8 == w) | (s8 == w)) & (C["role"] == "buy") & (C["so"] == 0) & (C["rank"] >= 0)) if len(G[C["mint"][k]]) >= 2]
        if len(k0) < 15: continue
        k0 = np.array(k0); f = C["rank"][k0] == 0
        beat_by_lower = 0; beat = 0; beat_hi = 0
        for k in k0[~f]:
            v = G[C["mint"][k]]; ahead = [x for x in v if C["i"][x] < C["i"][k]]
            beat += 1; beat_by_lower += any(tot[x] < tot[k] for x in ahead)
        ahead_of_higher = 0; nf = 0
        for k in k0[f]:
            v = G[C["mint"][k]]; nf += 1; ahead_of_higher += any(tot[x] > tot[k] for x in v[1:])
        print(f"{w}: contested {len(k0)}, first {f.mean():.0%}; tot p50 when first {np.median(ms(tot[k0[f]])) if f.any() else float('nan'):.2f} vs not {np.median(ms(tot[k0[~f]])) if (~f).any() else float('nan'):.2f} mSOL; "
              f"when first, a higher payer sat behind it {ahead_of_higher/max(nf,1):.0%}; when beaten, by a LOWER payer {beat_by_lower/max(beat,1):.0%}")

    # ---------- 7. AHwJSnFN close-up
    print("\n## 7. AHwJSnFN close-up [M]")
    w = "AHwJSnFN"; mw = (u8 == w) | (s8 == w)
    k0 = np.flatnonzero(mw & (C["role"] == "buy") & (C["so"] == 0) & (C["rank"] >= 0))
    others = [len(G[C["mint"][k]]) - 1 for k in k0]
    print(f"create-slot buys {len(k0)}; picks {C['pick'][k0].sum()}; other non-bundle create-slot buyers p50 {np.median(others):.0f}, share alone {np.mean(np.array(others)==0):.0%}")
    print(f"rel idx p50 {np.median(C['rel'][k0]):.0f}; jito bundle info {collections.Counter(C['jb'][k0]).most_common()}")
    fa = mw & (C["role"] == "fail")
    print(f"fails {fa.sum()} (so: {collections.Counter(C['so'][fa]).most_common(3)}), fail fee p50 {np.median(C['fee'][fa])} lamports; err {collections.Counter(C['err'][fa]).most_common(2)}")
    fl_ = collections.Counter(C["mint"][fa]); lm = set(C["mint"][k0])
    print(f"launches with an AHwJSnFN fail {len(fl_)}, of which it also landed {len(set(fl_) & lm)}; fails per launch p50 {np.median(list(fl_.values())):.0f}")
    pk = C["pick"][k0]
    print(f"on picks: first {np.mean(C['rank'][k0[pk]]==0):.0%} of {pk.sum()}; contested picks {sum(1 for k in k0[pk] if len(G[C['mint'][k]])>=2)}")

if __name__ == "__main__":
    main()
