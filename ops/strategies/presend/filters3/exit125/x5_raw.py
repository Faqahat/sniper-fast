#!/usr/bin/env python3
"""EXIT-125v200 step 5: raw pump.fun tape (collector txs_*.jsonl.gz) for chosen fills.
 (a) completeness check: every fill in a sample whose time the collector covers -> raw trades on the mint from the fill slot to the
     tape's last slot vs the hold tape's (slot, idx, j) set
 (b) extension: raw trades on the mint for slots past the hold tape (fill slot .. +16) for every fill, so landings past fill+3000 ms can
     be priced at slot resolution (raw has no rx times; the in-slot rx time is interpolated from idx, see x4).
Out: rawext.json {fill_sig: {"trades": [...], "slot_maxidx": {slot: max idx seen}, "files": n}}, rawcheck.json"""
import sys, os, glob, gzip, json, re, collections, random
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real")
import decode as DC   # parse_trade / chunks_of / DISC / HEAD (our own decoder, read-only use)
D = "/home/moiz/sniper-data/filters3/exit125"
C = "/home/moiz/sniper-data/collect"
F = json.load(open(f"{D}/fills.json"))["fills"]
files = []
for d in sorted(glob.glob(f"{C}/run_*/txs")):
    for fn in glob.glob(f"{d}/txs_*.jsonl.gz"):
        files.append((int(re.search(r"txs_(\d+)", fn).group(1)), fn))
files.sort()
starts = [a for a, _ in files]
def files_for(tsec):
    return [fn for a, fn in files if tsec - 330 <= a <= tsec + 15]

mode = sys.argv[1] if len(sys.argv) > 1 else "all"
want = {}
for x in F:
    if not x["sells"]: continue
    ts = x["t"] / 1e9
    fs = files_for(ts)
    if not fs: continue
    want[x["sig"]] = dict(mint=x["mint"], lo=x["slot"], hi=x["slot"] + 16, files=fs)
print("fills with raw files:", len(want), "of", len(F), flush=True)
byfile = collections.defaultdict(list)
for sig, w in want.items():
    for fn in w["files"]: byfile[fn].append(sig)
out = {sig: dict(trades=[], slot_maxidx={}, files=len(w["files"])) for sig, w in want.items()}
mints = collections.defaultdict(list)
for sig, w in want.items(): mints[w["mint"]].append(sig)
done = 0
for fn, sigs in sorted(byfile.items()):
    ms = {want[s]["mint"]: [] for s in sigs}
    for s in sigs: ms[want[s]["mint"]].append(s)
    lo = min(want[s]["lo"] for s in sigs); hi = max(want[s]["hi"] for s in sigs)
    smax = {}
    try:
        with gzip.open(fn, "rt") as f:
            for line in f:
                m = DC.HEAD.match(line)
                if not m: continue
                sl, ix = int(m.group(1)), int(m.group(2))
                if sl < lo or sl > hi: continue
                if ix > smax.get(sl, -1): smax[sl] = ix
                if DC.B64KEY not in line: continue
                hit = [mt for mt in ms if mt in line]
                if not hit: continue
                r = json.loads(line)
                if r.get("err") is not None: continue
                j = 0
                for b in DC.chunks_of(r.get("ev")):
                    if b[:8] != DC.DISC: continue
                    t = DC.parse_trade(b)
                    if t is None: continue
                    mint, sol, tok, buy, user, vsol, vtok, fb, cb = t
                    if mint in ms:
                        for s in ms[mint]:
                            if want[s]["lo"] <= sl <= want[s]["hi"]:
                                out[s]["trades"].append(dict(slot=sl, idx=ix, j=j, buy=bool(buy), sol=sol, tok=tok, vsol=vsol, vtok=vtok, w=user[:8], sig=r["sig"]))
                    j += 1
    except (EOFError, OSError) as ex:
        print("trunc", fn, repr(ex)[:60], flush=True)
    for s in sigs:
        for sl, ix in smax.items():
            if want[s]["lo"] <= sl <= want[s]["hi"]:
                out[s]["slot_maxidx"][sl] = max(out[s]["slot_maxidx"].get(sl, -1), ix)
    done += 1
    if done % 20 == 0: print("files", done, "of", len(byfile), flush=True)
for s in out:   # dedupe (a fill can read two files)
    seen = set(); tr = []
    for a in sorted(out[s]["trades"], key=lambda a: (a["slot"], a["idx"], a["j"])):
        k = (a["slot"], a["idx"], a["j"])
        if k not in seen: seen.add(k); tr.append(a)
    out[s]["trades"] = tr
json.dump(out, open(f"{D}/rawext.json", "w"))
# completeness check vs the hold tape
chk = collections.Counter(); ex = []
for x in F:
    s = x["sig"]
    if s not in out or not x["tape"]: continue
    last = max(a["slot"] for a in x["tape"])
    tape = {(a["slot"], a["idx"], a.get("j", 0)) for a in x["tape"] if a["slot"] >= x["slot"]}
    raw = {(a["slot"], a["idx"], a["j"]) for a in out[s]["trades"] if x["slot"] <= a["slot"] <= last}
    # slots fully inside the tape window: raw slot rows only up to the tape's last slot (its last slot may be cut at 3000 ms)
    rawfull = {k for k in raw if k[0] < last}
    tapefull = {k for k in tape if k[0] < last}
    chk["fills"] += 1
    chk["raw_trades"] += len(rawfull); chk["tape_trades"] += len(tapefull)
    chk["raw_not_in_tape"] += len(rawfull - tapefull); chk["tape_not_in_raw"] += len(tapefull - rawfull)
    if rawfull - tapefull: chk["fills_with_missing"] += 1; ex.append((x["run"], x["mint"], sorted(rawfull - tapefull)[:3]))
    if not out[s]["slot_maxidx"]: chk["no_raw_rows"] += 1
print(dict(chk)); print(ex[:10])
json.dump(dict(chk=dict(chk), ex=ex), open(f"{D}/rawcheck.json", "w"))
