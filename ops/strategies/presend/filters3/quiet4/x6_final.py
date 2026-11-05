#!/usr/bin/env python3
"""QUIET4 step 6: the proof table for the owner's requested families (one representative + the DEV-best of each) and the one DEV
survivor, ON TOP of QUIET + QUIET3-A + creator ledger; per period and per run, w/o top 5, the owner's r50 cases.
Writes /home/moiz/sniper-data/filters3/quiet4/final.json and prints the tables."""
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/filters3/quiet4")
import q4lib as L
import x3_grid as G

EXTRA = {
    "recent book rbl10 n>=5 mean<=0.5": G.r_recent_book("rbl10", 5, 0.5),
    "recent book rbl10 n>=5 mean<=1.5": G.r_recent_book("rbl10", 5, 1.5),
    "recent book rbl10 n>=8 mean<=1.0": G.r_recent_book("rbl10", 8, 1.0),
    "recent book rbl10 n>=5 mean<=1.0 T2+re": G.r_recent_book("rbl10", 5, 1.0, kinds=("T2", "rearm")),
    "recent book rbl5 n>=5 mean<=1.0": G.r_recent_book("rbl5", 5, 1.0),
}
G.RULES.update(EXTRA)
FAM = [
    ("CANDIDATE (only DEV survivor)", "recent book rbl10 n>=5 mean<=1.0"),
    ("  neighbour", "recent book rbl10 n>=5 mean<=0.5"),
    ("  neighbour", "recent book rbl10 n>=5 mean<=1.5"),
    ("  neighbour", "recent book rbl10 n>=8 mean<=1.0"),
    ("  neighbour", "recent book rbl5 n>=5 mean<=1.0"),
    ("  neighbour", "recent book rbl10 n>=5 mean<=1.0 T2+re"),
    ("owner: QUIET sig4 on RECENT whale dumps (3 h)", "QUIET sig4 on recent rb3h n>=3 fol<4.0"),
    ("owner: QUIET sig4 on last 10 dumps", "QUIET sig4 on recent rbl10 n>=3 fol<4.0"),
    ("owner(b): recent whale follower rate 1 h", "recent book rb1h n>=3 mean<=2.0"),
    ("owner(a): wh_fol shrinkage m=4 prior=1", "quiet shrink m=4 prior=1.0 T2"),
    ("owner(a): wh_fol shrinkage m=8 prior=2", "quiet shrink m=8 prior=2.0 T2"),
    ("owner(a): QUIET sig4 needs >= 8 dumps", "quiet min-dumps 8 T2"),
    ("owner(c): QUIET3-A whd<=4", "q3a widened n120<=15 whd<=4"),
    ("owner(c): QUIET3-A whd<=5", "q3a widened n120<=15 whd<=5"),
    ("whale ledger: last 3 (24h) all unfollowed", "whale last==3 unf (24h)"),
    ("whale ledger: n>=2 sum<=-0.05 (24h)", "whale sum n>=2 <=-0.05 (24h)"),
    ("whale ledger: dumped >=1 SOL on us (24h)", "whale dumped-on-us n>=1 sol>=1.0 (24h)"),
    ("whale shadow (incl skipped) 24h fills>=5 <=-0.02", "whale shadow 24h fills>=5 mean<=-0.02"),
    ("whale shadow 3h fills>=5 <=-0.015", "whale shadow 3h fills>=5 mean<=-0.015"),
    ("bait whale: >=5 triggers/24h & <=3 dumps", "bait ws24_n>=5 wh_dumps<=3"),
    ("bad-actor ledger (holder/creator/whale) n>=3 <=-0.1", "entity ent pct>=3 n>=3 <=-0.1 (allh)"),
    ("bad-actor ledger (sold into hold) n>=3 <=-0.1", "entity sell pct>=3 n>=3 <=-0.1 (allh)"),
    ("owner(d): repeat hold-seller holds>=2% (n>=3, 24h)", "repeat hold-seller n>=3 sol>=0.3 holds>=2% (24h)"),
    ("regime: our last 50 followed <=65%", "regime rg_fol50<=0.65"),
    ("regime(shadow 3h)<=-0.005 & n120<=10 & q1,q3", "regime rg_sh3h<=-0.005 & n120<=10 & q1,q3"),
    ("creator recent: last 2 in 3 h unfollowed", "creator recent last==2 unf 3h"),
]
CASES = ["7UQVd1kU", "8FCtPpMu", "Cj1hRfd5", "Gv3jDzEC"]

if __name__ == "__main__":
    names = [n for _, n in FAM]
    res = G.run(names)
    P = G.P
    byid = {p["id"]: p for p in P}
    r50_unf = [p for p in P if p["per"] == "R50" and p["pnl"] < 0 and not p["followed"]]
    out = {}
    print("ON TOP of QUIET + QUIET3-A + creator ledger 2:0.05. Saved SOL = -sum(realized P&L of blocked live positions). w5 = saved without its 5 biggest saves.")
    print("Hours: " + ", ".join(f"{k} {v:.1f} h" for k, v in G.H.items()))
    for lab, n in FAM:
        row = res[n]
        b = set(row["blocked_ids"])
        cases = [c for c in CASES if any(byid[i]["mint"].startswith(c) and byid[i]["per"] == "R50" and byid[i]["kind"] == "T2" for i in b)]
        flats = sum(1 for p in r50_unf if p["id"] in b)
        ok = all(row[p]["saved"] > 0 and row[p]["wo5"] > 0 for p in ("DEV", "VAL", "HOLD"))
        print(f"\n[{'PASS' if ok else 'fail'}] {lab}: {n}")
        print(G.fmt("", row)[52:])
        print(f"    per run: " + " ".join(f"{r} {v:+.3f}" for r, v in row["runs"].items() if v))
        print(f"    owner cases caught: {cases or 'none'} | r50 unfollowed losers caught {flats}/{len(r50_unf)}")
        out[n] = {"label": lab, "pass": ok, **{p: row[p] for p in L.PERS}, "runs": row["runs"], "cases": cases, "r50_unf_caught": flats}
        if lab.startswith("CANDIDATE"):
            print("    blocked:")
            for i in sorted(b):
                p = byid[i]
                print(f"      {L.pkt(p['t0'])} {p['run']} {p['kind']:<5} {p['mint']} whale {p['whale'][:8]} {p['pnl']:+.4f} {'followed' if p['followed'] else 'NOT followed'} rbl10 {G.RB[i]['rbl10']}")
    json.dump(out, open(f"{L.D}/final.json", "w"), indent=1)
