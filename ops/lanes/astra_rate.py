#!/usr/bin/env python3
"""ASTRA rate check: replay a run's real pre-send tick demand through the sender's three rate caps under other settings.

Demand (MEASURED from the run .jsonl): every armed window's ticks (the sender numbers each tick n = 1, 2, ... before its skip
checks, so sent tries + the missing n of each window = the ticks; a missing tick gets the time interpolated from its
neighbours; ticks while one of our positions was open are dropped: the sender pauses them before routing). Optional extra demand
(--rearm OBS.jsonl ...): the observatory's shadow re-arm windows (rule R0 = dip26's live re-arm), 8 ticks per slot from the arm
to the window's end (or its shadow fill).
Caps (pslive.rs take_rate, in this order; a refused tick takes no token and the window's next tick goes to the next path):
  rate_path        the route entry's token bucket: --presend-live-path-max-per-sec P, burst P/4 (one bucket per route ENTRY)
  rate_global      the global token bucket: --presend-live-max-per-sec G, burst G/4
  rate_path_config the path's [[send]] max_per_sec: at most C sends in any rolling second (send/budget.rs Budget::try_now)
Route entry of a tick = route[(n + w) % len(route)] (the engine's alternation; a path listed twice = 2:1 weighting).
Usage: astra_rate.py RUN.jsonl [--status-sent N] [--rearm OBS1.jsonl OBS2.jsonl ...] [--json OUT]"""
import sys, json, argparse, collections, bisect
from collections import deque
import numpy as np

IV_NS = 26.5e6          # MEASURED r37: tick interval median 26.53 ms (k 8 per ~212 ms slot)


class Bucket:
    """send/budget.rs TokenBucket: rate per s, holds at most `burst` tokens, starts full"""
    def __init__(self, rate, burst):
        self.rate = rate / 1e9; self.cap = float(burst); self.units = float(burst); self.last = None
    def _at(self, now): return self.units if self.last is None else min(self.cap, self.units + max(0, now - self.last) * self.rate)
    def peek(self, now): return self._at(now) >= 1.0 - 1e-12
    def take(self, now):
        self.units = self._at(now)
        if self.last is None or now > self.last: self.last = now
        self.units -= 1.0

class Window1s:
    """send/budget.rs Budget::try_now: at most `per_sec` sends in any rolling second"""
    def __init__(self, per_sec): self.n = per_sec; self.q = deque()
    def try_now(self, now):
        while self.q and now - self.q[0] >= 1e9: self.q.popleft()
        if len(self.q) >= self.n: return False
        self.q.append(now); return True


def demand(fn):
    """[(t_ns, window key, n)] of a run's ticks + the windows' spans"""
    A = collections.defaultdict(dict); fills = []; sells = collections.defaultdict(list); seg = -1
    for l in open(fn, errors="replace"):
        if '"ev":"run_start"' in l: seg += 1; continue
        if '"ev":"presend_' not in l: continue
        try: r = json.loads(l)
        except Exception: continue
        e = r["ev"]
        if e == "presend_attempt": A[(max(seg, 0), r["w"])].setdefault(r["n"], r["t"])
        elif e == "presend_live_fill": fills.append((r["t"], r["mint"]))
        elif e == "presend_live_sell_land": sells[r["mint"]].append(r["t"])
    # positions open: fill -> its last sell landing + 300 ms (the sender pauses every window meanwhile: one position per server)
    opn = []
    for t, m in fills:
        after = [s for s in sells.get(m, []) if s >= t]
        opn.append((t, (min(after) if after else t + 1.2e9) + 3e8))
    opn.sort(); ost = [a for a, _ in opn]
    def paused(t):
        k = bisect.bisect_right(ost, t) - 1
        return k >= 0 and opn[k][0] <= t <= opn[k][1]
    ticks = []; gaps = 0; gaps_paused = 0
    for k, d in A.items():
        ns = sorted(d)
        for n in range(1, ns[-1] + 1):
            if n in d: ticks.append((d[n], k, n)); continue
            lo = max((x for x in ns if x < n), default=None); hi = min((x for x in ns if x > n), default=None)
            if lo is None: t = d[hi] - (hi - n) * IV_NS
            elif hi is None: t = d[lo] + (n - lo) * IV_NS
            else: t = d[lo] + (d[hi] - d[lo]) * (n - lo) / (hi - lo)
            gaps += 1
            if paused(t): gaps_paused += 1; continue
            ticks.append((int(t), k, n))
    ticks.sort()
    return ticks, A, gaps, gaps_paused

def rearm_windows(files, t_lo, t_hi):
    """the observatory's shadow re-arm windows (rearm_window records): ticks every 26.5 ms from the arm to the end / shadow fill"""
    out = []; i = 0
    for fn in files:
        for l in open(fn, errors="replace"):
            if '"ev":"rearm_window"' not in l: continue
            try: r = json.loads(l)
            except Exception: continue
            a = (r.get("arm") or {}).get("t"); e = (r.get("end") or {}).get("t")
            f = (((r.get("rows") or {}).get("a") or {}).get("fill") or {}).get("a_land")
            if not a or not e: continue
            if f and a <= f < e: e = f
            if not (t_lo <= a <= t_hi): continue
            i += 1; n = 0; t = a + 50e6
            while t < e: n += 1; out.append((int(t), ("re", i), n)); t += IV_NS
    out.sort()
    return out, i

def simulate(ticks, route, G, P, C):
    """-> per path: sent, skips by reason; per route entry buckets; astralane binding stats"""
    gb = Bucket(G, max(int(G) // 4, 1))
    pb = [Bucket(P, max(int(P) // 4, 1)) for _ in route]
    cb = {p: Window1s(C[p]) for p in set(route)}
    st = {p: collections.Counter() for p in set(route)}
    refused_sec = {p: set() for p in set(route)}; per_win = collections.defaultdict(collections.Counter)
    for t, k, n in ticks:
        i = (n + (k[1] if isinstance(k[1], int) else 0)) % len(route); p = route[i]
        st[p]["ticks"] += 1
        if not pb[i].peek(t): st[p]["rate_path"] += 1; refused_sec[p].add(t // 10**9); continue
        if not gb.peek(t): st[p]["rate_global"] += 1; refused_sec[p].add(t // 10**9); continue
        if not cb[p].try_now(t): st[p]["rate_path_config"] += 1; refused_sec[p].add(t // 10**9); continue
        pb[i].take(t); gb.take(t); st[p]["sent"] += 1; per_win[k][p] += 1
    return st, refused_sec, per_win

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("run"); ap.add_argument("--rearm", nargs="*", default=[]); ap.add_argument("--json")
    ap.add_argument("--status", default=None, help="the engine's not-sent counts at the end of this file, e.g. 'rate_path=46,rate_path_config=309,paused=154'")
    a = ap.parse_args()
    ticks, A, gaps, gp = demand(a.run)
    t0, t1 = ticks[0][0], ticks[-1][0]; hrs = (t1 - t0) / 3.6e12
    sent_real = sum(len(d) for d in A.values())
    print(f"DEMAND {a.run}: {len(A)} windows, {len(ticks)} ticks over {hrs:.1f} h (sent {sent_real} + visible skipped ticks {gaps}, of them {gp} while a position was open = not demand)")
    # concurrency + per-second demand
    span = {}
    for t, k, n in ticks: lo, hi = span.get(k, (t, t)); span[k] = (min(lo, t), max(hi, t))
    ev = sorted([(lo, 1) for lo, hi in span.values()] + [(hi + IV_NS, -1) for lo, hi in span.values()])
    cur = 0; last = ev[0][0]; tm = collections.Counter()
    for t, d in ev:
        tm[cur] += t - last; cur += d; last = t
    tot = sum(v for k, v in tm.items() if k > 0)
    print("  windows armed at once (share of armed time): " + ", ".join(f"{k}: {v / tot:.1%}" for k, v in sorted(tm.items()) if k > 0))
    sec = collections.Counter(t // 10**9 for t, _, _ in ticks)
    v = np.array(list(sec.values()))
    print(f"  ticks per busy second: p50 {np.percentile(v, 50):.0f}, p90 {np.percentile(v, 90):.0f}, p99 {np.percentile(v, 99):.0f}, max {v.max()}; "
          f"seconds with > 40 ticks: {(v > 40).sum()}, > 60: {(v > 60).sum()} (of {len(v)} busy seconds)")
    extra = []
    if a.rearm:
        extra, nre = rearm_windows(a.rearm, t0, t1)
        print(f"  + dip26 re-arm (observatory shadow, rule R0): {nre} windows, {len(extra)} ticks (+{len(extra) / len(ticks):.0%} demand)")
    H, AS = "helius-ps", "astralane-ps"
    SC = [("r37 as run (check)", [H], 40, 40, {H: 40}, False),
          ("today's caps, 2 paths 1:1", [H, AS], 40, 40, {H: 40, AS: 19}, False),
          ("global 60, 1:1, astra 19", [H, AS], 60, 40, {H: 40, AS: 19}, False),
          ("global 60, 1:1, astra 20", [H, AS], 60, 40, {H: 40, AS: 20}, False),
          ("global 50, 1:1, astra 19", [H, AS], 50, 40, {H: 40, AS: 19}, False),
          ("global 60, 2:1 (H,H,A), astra 19", [H, H, AS], 60, 40, {H: 40, AS: 19}, False),
          ("global 60, 2:1 (H,H,A), path 20", [H, H, AS], 60, 20, {H: 40, AS: 19}, False),
          ("global 60, 1:1, astra 19 + RE-ARM", [H, AS], 60, 40, {H: 40, AS: 19}, True),
          ("global 60, 2:1, astra 19 + RE-ARM", [H, H, AS], 60, 40, {H: 40, AS: 19}, True)]
    res = []
    print()
    print(f"{'scenario':36s} {'ticks':>6s} | {'helius-ps sent':>14s} {'skips p/g/c':>13s} | {'astralane-ps sent':>17s} {'skips p/g/c':>13s} {'A refused':>9s} {'A-cap sec':>9s} | "
          f"{'A share':>7s} {'1:1 windows':>11s}")
    for name, route, G, P, C, re in SC:
        if re and not extra: continue
        tk = sorted(ticks + extra) if re else ticks
        st, rs, pw = simulate(tk, route, G, P, C)
        h = st.get(H, collections.Counter()); s = st.get(AS, collections.Counter())
        sent_all = sum(x["sent"] for x in st.values())
        a_share = s["sent"] / sent_all if sent_all else 0
        bal = [c[AS] / (c[AS] + c[H]) for c in pw.values() if c[AS] + c[H] >= 4]
        near = np.mean([abs(b - 0.5) <= 0.1 for b in bal]) if (bal and AS in route and route.count(H) == 1) else float("nan")
        ref = s["ticks"] - s["sent"]
        row = {"scenario": name, "route": route, "G": G, "P": P, "C": C, "ticks": len(tk), "helius_sent": h["sent"], "helius_skips": [h["rate_path"], h["rate_global"], h["rate_path_config"]],
               "astra_sent": s["sent"], "astra_skips": [s["rate_path"], s["rate_global"], s["rate_path_config"]], "astra_refused_share": ref / s["ticks"] if s["ticks"] else None,
               "astra_cap_seconds": len(rs.get(AS, ())), "astra_share": a_share, "windows_near_1to1": near}
        res.append(row)
        print(f"{name:36s} {len(tk):6d} | {h['sent']:14d} {h['rate_path']:4d}/{h['rate_global']:3d}/{h['rate_path_config']:4d} | "
              + (f"{s['sent']:17d} {s['rate_path']:4d}/{s['rate_global']:3d}/{s['rate_path_config']:4d} {ref / max(s['ticks'], 1):9.1%} {len(rs.get(AS, ())):9d} | {a_share:7.1%} "
                 f"{near:11.0%}" if AS in route else f"{'-':>17s} {'-':>13s} {'-':>9s} {'-':>9s} | {'-':>7s} {'-':>11s}"))
    print()
    print("skips p/g/c = rate_path (route entry bucket) / rate_global / rate_path_config (the path's [[send]] max_per_sec, rolling 1 s)")
    print("A refused = share of the ticks routed to astralane-ps that it refused; A-cap sec = seconds with at least one refused astralane tick;")
    print("A share = astralane's share of all sent tries; 1:1 windows = windows (>= 4 sent) whose astralane share is within 40-60%")
    if a.json: json.dump(res, open(a.json, "w"), indent=1)

if __name__ == "__main__":
    main()
