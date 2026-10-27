#!/usr/bin/env python3
# SPEED TRUTH step 8: compact markdown tables for the report (p10/p50/p90 by client, server, landed path, run).
import json, sys, os, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tl
R = json.load(open(f"{tl.OUT}/timeline.json"))
SS = {int(k): v for k, v in json.load(open(f"{tl.OUT}/slot_stats.json")).items()}
def size(s): v = SS.get(s); return v[1] + 1 if v else None
B400 = lambda s, i: s * tl.SMS + i / max(400, i + 1) * tl.SMS
def feed(r): return ((r["land"]["t"] if r["land"] else r["fail"]["t"]) - r["t_dump_rx"]) / 1e6
def b4(r): c = r["C"]; return B400(c["our_slot"], c["our_idx"]) - B400(c["dump_slot"], c["dump_idx"])
def p3(v, f="{:.0f}"): return tl.pct(v, (10, 50, 90), f).replace(" / ", "/")
def table(title, groups):
    print(f"\n**{title}**\n")
    print("| group | n | fill | 1st write ms | landing ms (feed) | landing ms (B400) | same slot |")
    print("|---|---|---|---|---|---|---|")
    for g, sel in groups:
        if not sel: continue
        print(f"| {g} | {len(sel)} | {sum(r['filled'] for r in sel) / len(sel):.0%} | {p3([r['W']['first_write'] for r in sel], '{:.1f}')} | "
              f"{p3([feed(r) for r in sel])} | {p3([b4(r) for r in sel])} | {sum(1 for r in sel if r['C']['slot_delta'] == 0) / len(sel):.0%} |")
cls = lambda r: r["L"]["dump_class"]
table("All", [("all", R), ("fills", [r for r in R if r["filled"]]), ("fails", [r for r in R if not r["filled"]])])
table("By server", [(s, [r for r in R if r["srv"] == s]) for s in ("FRA", "AMS")])
table("By leader client", [(c, [r for r in R if cls(r) == c]) for c in ("bam", "harmonic", "jito", "fd", "firebam", "rakurai")])
table("By landed path (nonce runs)", [(p, [r for r in R if r["nonce"] and r["C"]["our_path"] == p]) for p in ("nozomi", "staked-rpc", "helius", "landx-fra3", "helius-swqos", "jito-bundle", "bolt")])
table("By run", [(f"{s} r{n}", [r for r in R if r["srv"] == s and r["run"] == n]) for s, n, _ in tl.RUNS])
