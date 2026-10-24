import json, gzip, collections, sys
TOP = [l.strip() for l in open(sys.argv[1]) if l.strip()]
rows = collections.defaultdict(list)
for line in gzip.open((sys.argv[2] if len(sys.argv) > 2 else "/home/moiz/sniper/ops/agents/topearners/work/txrows.jsonl.gz"), "rt"):
    x = json.loads(line)
    if x["w"] in TOP: rows[x["w"]].append(x)
def q(v, ps=(10, 50, 90)):
    v = sorted(v)
    if not v: return "-"
    return "/".join(f"{v[min(len(v)-1, int(p/100*len(v)))]:g}" for p in ps)
for w in TOP:
    R = rows[w]
    if not R: print(w, "no rows"); continue
    ok = [x for x in R if x["ok"]]; bad = [x for x in R if not x["ok"]]
    print("=" * 100); print(w, "txs", len(R), "ok", len(ok), "fail", len(bad))
    print("  kinds ok", dict(collections.Counter(x["kind"] for x in ok)), "fail", dict(collections.Counter(x["kind"] for x in bad)))
    for kind in ("buy", "sell"):
        K = [x for x in ok if x["kind"] == kind]
        if not K: continue
        rel = collections.Counter(tuple(sorted(set(t[0] for t in x["tips"]))) for x in K)
        ntip = collections.Counter(len(x["tips"]) for x in K)
        tipsum = [sum(t[1] for t in x["tips"]) / 1e9 for x in K]
        tipsum_nz = [t for t in tipsum if t > 0]
        pf = [((x["fee"] or 0) - 5000 * x["nsig"]) / 1e9 for x in K]
        print(f"  [{kind}] n={len(K)} relays={rel.most_common(6)} ntips={dict(ntip)}")
        print(f"        tip SOL p10/50/90 (tipped only)={q(tipsum_nz)}  frac_tipped={len(tipsum_nz)/len(K):.2f}  prio-fee SOL p10/50/90={q(pf)}")
        print(f"        cup p10/50/90={q([x['cup'] or 0 for x in K])} cul={q([x['cul'] or 0 for x in K])} cu={q([x['cu'] or 0 for x in K])} nsig={dict(collections.Counter(x['nsig'] for x in K))} payer==w {sum(x['payer']==w for x in K)/len(K):.2f} wpos={dict(collections.Counter(x['wpos'] for x in K))}")
        print(f"        progs={collections.Counter(tuple(x['progs']) for x in K).most_common(3)}")
        print(f"        ixn={collections.Counter(tuple(x['ixn']) for x in K).most_common(3)}")
        if kind == "buy":
            # tip per relay
            per = collections.defaultdict(list)
            for x in K:
                for t in x["tips"]: per[t[0]].append(t[1] / 1e9)
            print("        tip per relay:", {k: (len(v), q(v)) for k, v in sorted(per.items(), key=lambda kv: -len(kv[1]))[:8]})
            tipacc = collections.Counter(t[2] for x in K for t in x["tips"])
            print("        distinct tip accounts:", len(tipacc), tipacc.most_common(4))
    if bad:
        print(f"  [fail] fee SOL total={sum(x['fee'] or 0 for x in bad)/1e9:.3f} fee p10/50/90={q([(x['fee'] or 0)/1e9 for x in bad])} cup={q([x['cup'] or 0 for x in bad])} cu={q([x['cu'] or 0 for x in bad])}")
        print(f"        errs={collections.Counter(tuple(x['ec']) if x['ec'] else None for x in bad).most_common(6)}")
        print(f"        progs={collections.Counter(tuple(x['progs']) for x in bad).most_common(2)}  ixn={collections.Counter(tuple(x['ixn']) for x in bad).most_common(3)}")
        print(f"        payer==w {sum(x['payer']==w for x in bad)/len(bad):.2f} nsig={dict(collections.Counter(x['nsig'] for x in bad))}")
