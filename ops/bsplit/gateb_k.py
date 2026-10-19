# Gate B on the FRESH forward run: enter right after the k-th OUTSIDE buy in slot S (vs fixed tx positions). Paper/read-only.
import sys, runpy, io, contextlib, statistics as st
tag = sys.argv[1] if len(sys.argv) > 1 else "fresh"
sys.argv = ["forward_proof.py", tag]
with contextlib.redirect_stdout(io.StringIO()):
    g = runpy.run_path("/root/race/forward_proof.py", run_name="__main__")
F, sim, days, EX = g["F"], g["sim"], g["days"], g["EXITS"]["time 1s"]
gate = lambda o: o["dev_sol"] >= 3 and o["glued"] >= 2 and o["n_len"] <= 12
G = [o for o in F if gate(o)]
print(f"run {tag}: scored {len(F)} launches over {days*24:.1f} h; Gate B fires {len(G)} ({len(G)/days:.0f}/day)")


def row(name, dfun):
    v = [sim(o, EX, d_land=dfun(o), land_s1=False, size=2.0) for o in G]
    ex = sorted(v)[:-3]
    print(f"  {name:34} n={len(v):4} mean {st.mean(v):+6.1%} med {st.median(v):+6.1%} ex-top3 {st.mean(ex):+6.1%} "
          f"win {sum(x > 0 for x in v)/len(v):4.0%} | SOL/day @2 SOL {st.mean(v)*2*len(G)/days:+7.1f}")


def after_k(k):
    def f(o):
        ds = o["outS_d"]
        if len(ds) >= k:
            return ds[k - 1] + 1
        return (ds[-1] + 1) if ds else max(1, o["glued"] + 1)
    return f


print("entry right after the k-th outside buy in S (if fewer exist, right after the last one / after the bundle):")
for k in (1, 2, 3, 5, 10):
    row(f"after outside buy #{k}", after_k(k))
print("reference, fixed position after the create (txs):")
for d in (5, 10, 25, 50, 100):
    row(f"at tx #{d}", lambda o, d=d: d)
print("how many outside buys are ahead of tx #25 / #100 on Gate B launches (median):",
      st.median(sum(1 for x in o["outS_d"] if x < 25) for o in G), "/", st.median(sum(1 for x in o["outS_d"] if x < 100) for o in G))
