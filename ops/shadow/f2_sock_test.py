#!/usr/bin/env python3
# Local test of the scorer's FINAL2_SOCK serve mode: replay the last N launches of a recorded shadow engine log as the
# engine would send them (RACE seen line + RACE decide line + DETECT time/kind/quote), measure the round trip, and
# compare the socket's pick with the shadow's recorded final_pick (history differs a little: the test scorer's history
# is "now", the shadow's was "then"). usage: python3 -I f2_sock_test.py <engine log> <scores_v3.jsonl> <sock> [N=150]
import sys, re, json, socket, time, collections
LOG, SC, SOCK = sys.argv[1:4]; N = int(sys.argv[4]) if len(sys.argv) > 4 else 150
KV = re.compile(r"(\w+)=(\S*)")
det, seen, dec = {}, {}, {}
for l in open(LOG, errors="replace"):
    if "DETECT" in l and " first=1 " in l:
        d = dict(KV.findall(l)); m = d.get("mint")
        if m and m not in det: det[m] = d
    elif "RACE seen" in l:
        m = dict(KV.findall(l)).get("mint"); seen[m] = l.strip()
    elif "RACE decide" in l:
        m = dict(KV.findall(l)).get("mint"); dec[m] = l.strip()
shadow = {}
for l in open(SC):
    try: r = json.loads(l)
    except Exception: continue
    if r.get("type") == "decide" and "final_pick" in r: shadow[r["mint"]] = r
ms = [m for m in dec if m in seen and m in det and m in shadow and det[m].get("quote") == "sol"][-N:]
# make sure some picks are in the sample
picks = [m for m in dec if m in seen and m in det and shadow.get(m, {}).get("final_pick")][-25:]
ms = list(dict.fromkeys(ms + picks))
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.connect(SOCK); f = s.makefile("rb")
lat, agree, n, rows = [], 0, 0, []
for m in ms:
    q = dict(seen=seen[m], decide=dec[m], t=int(det[m].get("t_rx", 0) or 0) / 1e9, kind=det[m].get("kind"), quote=det[m].get("quote"))
    t0 = time.perf_counter(); s.sendall((json.dumps(q) + "\n").encode()); rep = json.loads(f.readline()); dt = (time.perf_counter() - t0) * 1e6
    lat.append(dt); n += 1; sp = shadow[m]["final_pick"]; agree += (rep.get("pick") == sp)
    rows.append((m, sp, rep.get("pick"), rep.get("score"), shadow[m].get("final_score"), rep.get("err")))
lat.sort()
print(f"queries {n}: round trip median {lat[n // 2]:.0f} us, p90 {lat[int(n * 0.9)]:.0f} us, max {lat[-1]:.0f} us")
print(f"pick agreement with the shadow's recorded final_pick: {agree}/{n}; shadow picks in sample {sum(1 for r in rows if r[1])}, socket picks {sum(1 for r in rows if r[2])}")
print("errors:", collections.Counter(r[5] for r in rows if r[5]))
d = [abs((r[3] or 0) - (r[4] or 0)) for r in rows if r[3] is not None and r[4] is not None]
print(f"|score difference| median {sorted(d)[len(d) // 2]:.4f}, share < 0.01: {sum(1 for x in d if x < 0.01) / len(d):.0%}")
for r in rows:
    if r[1] != r[2]: print("   differs:", r[0][:10], "shadow", r[1], round(r[4], 3), "socket", r[2], round(r[3] or 0, 3))
