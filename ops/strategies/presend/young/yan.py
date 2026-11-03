"""YOUNG analysis helpers: hours covered (union of run spans, train/test), stats, bootstrap."""
import pickle, random, collections, datetime
from ylib import *
meta, _, _ = load() if False else (None, None, None)
import json
M = json.load(open(f"{D}/trig.json"))["meta"]
def spans():
    iv = sorted((m["t0"], m["t1"]) for m in M)
    u = []
    for a, b in iv:
        if u and a <= u[-1][1]: u[-1][1] = max(u[-1][1], b)
        else: u.append([a, b])
    return u
def hours(test=None):
    cut = (CUT - datetime.timedelta(hours=5) - datetime.datetime(1970, 1, 1)).total_seconds() * 1e9
    h = 0
    for a, b in spans():
        if test is True: a = max(a, cut)
        if test is False: b = min(b, cut)
        if b > a: h += (b - a) / 3.6e12
    return h
def boot(v, n=2000, seed=1):
    rnd = random.Random(seed); s = []
    for _ in range(n): s.append(sum(rnd.choice(v) for _ in v))
    s.sort(); return s[int(n * .05)], s[int(n * .95)]
def wo_top(v, k=5): return sum(sorted(v)[:-k]) if len(v) > k else 0.0
