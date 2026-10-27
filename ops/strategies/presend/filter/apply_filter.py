#!/usr/bin/env python3
"""PRE-SEND FILTER - apply the filter configs to one live run's records + the raw chain recording, and print before / after.

  python3 apply_filter.py --run ams:r26                 # records: local copy, else fetched read-only from the server (sudo cat)
  python3 apply_filter.py --run ams:r24 --run ams:r25   # several runs, one table each
  options: --live PATH (a dip_*.jsonl to use instead)   --rec DIR [DIR ...] (collector run dirs; default: every run_* under
           /home/moiz/sniper-data/collect)               --config quiet|c5|c5a|all (default all)   --list (print every removed fill)
           --procs N (raw-recording readers, default 12)

What it measures (all MEASURED from the engine records + chain, at the run's own size):
  per armed window: its fill (realized + token-account rent back) and its failed-try fees (land record; a try logged 'unseen' is
  looked up on the chain). Before = all windows; after = what the config keeps.
CONFIGS (rules from ops/strategies/presend/filter/REPORT; only data known before each decision is used):
  c5a  : STOP a window at trigger + 6 slots if NO other wallet (not the whale, not us) traded the token since the trigger
  c5   : STOP a window at trigger + 6 slots if FEWER THAN 2 other trades since the trigger
  quiet: c5 + do not ARM when all four quiet signals hold at the trigger:
           (1) no other trade earlier in the trigger's slot (last trade before the trigger is >= 1 slot older)
           (2) no wallet of cohort_train.json (the engine's --dip-cohort list) holds the token
           (3) fewer than 2 wallets of fbots_frozen.json ever traded the token
           (4) the whale's dumps of the last 24 h drew on average < 2.24 other buyers within 2 slots (or it has none):
               dump = a sell >= 0.3 SOL that drops the price >= 8% by itself, curve < 100 SOL
  'other trades' for the stop rules = the token's trades the engine had seen when it signed that try (the try record's 'pos').
  A fill whose own try a stop rule would not have sent is removed; the window's later tries are then charged as if it ran to its end
  (conservative). A skipped window is not replaced by a later trigger on the same token (rare; not modelled).
Read-only: local files, plus `ssh ... sudo cat` of the run records when no local copy exists. Nothing is sent."""
import sys, os, re, json, glob, gzip, base64, struct, argparse, collections, subprocess, time
import numpy as np
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
LOCAL = "/home/moiz/sniper-data/presend_filter/live"
COLLECT = "/home/moiz/sniper-data/collect"
COHORT = "/home/moiz/sniper/ops/overnight/sel/cohort_train.json"
FBOTS = f"{HERE}/fbots_frozen.json"
SERVERS = {"ams": "it@84.32.104.202", "fra": "it@84.32.100.36"}
WALLETS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}   # AMS, FRA
DISC = bytes.fromhex("bddb7fd34ee661ee"); CPI = bytes.fromhex("e445a52e51cb9a1d")
A58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
HIST_H = 30            # hours of chain read before the first trigger (token histories + 24 h whale history)
G = {}


# ----------------------------------------------------------------------------------------------------------- engine records
def run_file(run):
    region, r = run.split(":")
    name = f"dip_ams_{r}.jsonl" if region == "ams" else f"dip_{r}.jsonl"
    return region, name


def get_records(run, live=None):
    if live: return live
    region, name = run_file(run)
    for cand in (f"{LOCAL}/{name}", f"{LOCAL}/{region}_{name}"):
        if os.path.exists(cand): return cand
    os.makedirs(f"{LOCAL}/fetched", exist_ok=True)
    out = f"{LOCAL}/fetched/{region}_{name}"
    print(f"fetching {name} from {region} (read-only sudo cat) ...", flush=True)
    with open(out + ".tmp", "wb") as f:
        subprocess.run(["ssh", "-p", "1996", SERVERS[region], f"sudo cat /root/prod/runs/{name}"], stdout=f, check=True, timeout=600)
    os.rename(out + ".tmp", out)
    return out


def parse(fn):
    seg = 0
    W = collections.OrderedDict(); att = {}; land = {}; ata = []
    for line in open(fn):
        if '"ev":"presend_' not in line and '"ev":"run_start"' not in line: continue
        try: r = json.loads(line)
        except Exception: continue
        ev = r.get("ev")
        if ev == "run_start": seg += 1; continue
        r["seg"] = seg
        if ev == "presend_live_arm": W[(seg, r["w"])] = dict(seg=seg, w=r["w"], arm=r, fills=[], close=None, realized=None, atts=[])
        elif ev == "presend_attempt":
            att[r["sig"]] = r
            if (seg, r["w"]) in W: W[(seg, r["w"])]["atts"].append(r["sig"])
        elif ev == "presend_attempt_land": land[r["sig"]] = r
        elif ev == "presend_live_fill" and (seg, r["w"]) in W: W[(seg, r["w"])]["fills"].append(r)
        elif ev == "presend_live_close" and (seg, r["w"]) in W: W[(seg, r["w"])]["close"] = r
        elif ev == "presend_live_realized" and (seg, r["w"]) in W: W[(seg, r["w"])]["realized"] = r
        elif ev == "presend_live_ata_close": ata.append(r)
    return W, att, land, ata


# ----------------------------------------------------------------------------------------------------------- raw recording
def b58(b):
    n = int.from_bytes(b, "big"); s = []
    while n: n, r = divmod(n, 58); s.append(A58[r])
    return "1" * (len(b) - len(b.lstrip(b"\0"))) + "".join(reversed(s))


def read_chunk(fn):
    lo, hi = G["span"]
    T = []; F = {}
    try:
        with gzip.open(fn, "rt") as f:
            for line in f:
                ok = '"err":null' in line
                if ok and '"ev":[]' in line: continue
                if not ok and not any(w in line for w in WALLETS): continue
                try: r = json.loads(line)
                except Exception: continue
                bt = r.get("bt", 0)
                if bt < lo or bt > hi: continue
                if not ok:
                    sg = (r.get("signers") or ["?"])[0]
                    if sg in WALLETS: F[r["sig"]] = (r["s"], r["i"], r.get("fee") or 0)
                    continue
                evs = r.get("ev")
                if isinstance(evs, str):
                    try: evs = json.loads(evs)
                    except Exception: evs = []
                j = 0
                for e in evs or []:
                    for ch in e.split(" "):
                        try: b = base64.b64decode(ch + "=" * (-len(ch) % 4))
                        except Exception: continue
                        if b[:8] == CPI: b = b[8:]
                        if b[:8] != DISC or len(b) < 225: continue
                        o = 8
                        mint = b58(b[o:o + 32]); o += 32
                        sol, tok = struct.unpack_from("<QQ", b, o); o += 16
                        buy = b[o]; o += 1
                        user = b58(b[o:o + 32]); o += 40
                        vsol, vtok = struct.unpack_from("<QQ", b, o)
                        T.append((r["s"], r["i"], j, bt, mint, user, buy, sol, tok, vsol, vtok))
                        j += 1
    except (EOFError, OSError):
        pass
    return T, F


def load_chain(span, recs, procs):
    files = []
    for d in recs:
        for f in glob.glob(f"{d}/txs/txs_*.jsonl.gz"):
            ts = int(os.path.basename(f)[4:14])
            if span[0] - 400 <= ts <= span[1]: files.append(f)
    files.sort(key=lambda f: int(os.path.basename(f)[4:14]))
    G["span"] = span
    print(f"reading {len(files)} raw chunks ({time.strftime('%m-%d %H:%M', time.gmtime(span[0] + 18000))} -> "
          f"{time.strftime('%m-%d %H:%M', time.gmtime(span[1] + 18000))} PKT) ...", flush=True)
    rows = []; fails = {}
    with Pool(procs) as p:
        for T, F in p.imap_unordered(read_chunk, files):
            rows += T; fails.update(F)
    rows.sort(key=lambda x: (x[0], x[1], x[2]))
    out = []; last = None; pool = {}
    for x in rows:
        k = (x[0], x[1], x[2])
        if k == last: continue
        last = k
        m = pool.setdefault(x[4], x[4]); u = pool.setdefault(x[5], x[5])
        out.append((x[0], x[1], x[2], x[3], m, u) + x[6:])
    return out, fails


# ----------------------------------------------------------------------------------------------------------- features
class ChainIx:
    def __init__(self, rows):
        self.rows = rows
        self.by_mint = collections.defaultdict(list)
        for k, x in enumerate(rows): self.by_mint[x[4]].append(k)
        # dumps (all tokens): seller -> [(slot, bt, distinct other buyers in its slot (after it) and the next 2 slots)]
        self.dumps = collections.defaultdict(list)
        for mint, ks in self.by_mint.items():
            for a, k in enumerate(ks):
                s, i, j, bt, _, u, buy, sol, tok, vs, vt = rows[k]
                if buy or sol < 300_000_000 or vs >= 100_000_000_000 or vt <= tok: continue
                p = vs / max(vt, 1); pre = (vs + sol) / max(vt - tok, 1)
                if p > 0.92 * pre: continue
                bs = set()
                for k2 in ks[a + 1:]:
                    x2 = rows[k2]
                    if x2[0] > s + 2: break
                    if x2[6] and x2[5] != u: bs.add(x2[5])
                self.dumps[u].append((s, bt, len(bs)))


def quiet_signals(C, mint, trig, arm_t, cohort, fbots):
    ks = C.by_mint.get(mint, [])
    pos = None
    for a, k in enumerate(ks):
        x = C.rows[k]
        if (x[0], x[1], x[2]) == (trig["slot"], trig["idx"], trig.get("j", 0)): pos = a; break
    if pos is None: return None
    pre = [C.rows[k] for k in ks[:pos]]
    s0 = trig["slot"]
    since_last = s0 - pre[-1][0] if pre else 9999
    bal = collections.defaultdict(int); seen = set()
    for x in pre:
        bal[x[5]] += x[8] if x[6] else -x[8]; seen.add(x[5])
    coh_hold = sum(1 for w in seen if w in cohort and bal[w] > 0)
    fb_n = sum(1 for w in seen if w in fbots)
    tb = arm_t / 1e9
    d = [nf for s, bt, nf in C.dumps.get(trig["wallet"], []) if s + 2 < s0 and bt >= tb - 24 * 3600]
    wdf = float(np.mean(d)) if d else -1.0
    return dict(since_last=since_last, coh_hold=coh_hold, fb_n=fb_n, wh_dump_fol=wdf, k_trig=pos)


def others_seen(C, mint, k_trig, whale, pos):
    n = 0
    for k in C.by_mint[mint][k_trig + 1:]:
        x = C.rows[k]
        if (x[0], x[1], x[2]) > tuple(pos): break
        if x[5] != whale and x[5] not in WALLETS: n += 1
    return n


# ----------------------------------------------------------------------------------------------------------- one run
def windows(run, fn, C, our_fails, cohort, fbots):
    W, att, land, ata = parse(fn)
    used = set(); out = []
    for (seg, w), X in W.items():
        a = X["arm"]; tr = a["trig"]; arm_t = a.get("t") or tr["t"]
        fill_sig = X["fills"][0]["sig"] if X["fills"] else None
        tries = []
        for sig in X["atts"]:
            A = att[sig]; L = land.get(sig) or {}
            res = L.get("res"); fee = 0
            if res not in ("ok", None, "unseen"): fee = L.get("fee") if L.get("fee") is not None else 5120
            elif sig in our_fails: fee = our_fails[sig][2]
            tries.append(dict(slot=A["slot"], fee=fee, fill=(sig == fill_sig), pos=tuple(A.get("pos") or (0, 0, 0))))
        row = dict(run=run, seg=seg, w=w, mint=tr["mint"], t=arm_t, trig=tr, en_slot=a["en_slot"], tries=tries, fail_fee=sum(t["fee"] for t in tries),
                   filled=bool(X["fills"]), k=a.get("k") or 4)
        if X["fills"]:
            f = X["fills"][0]; rz = X["realized"] or {}; cl = X["close"] or {}
            rb = 0
            for q, z in enumerate(ata):
                if q in used: continue
                if z["seg"] == seg and z["mint"] == tr["mint"] and z.get("slot", 0) >= f["slot"]: rb = z.get("delta") or 0; used.add(q); break
            row.update(net=(rz.get("pnl") or 0) + rb, fill_slot=f["slot"], fill_idx=f["idx"])
            sl = cl.get("sell_lands") or ([cl["sell_land"]] if cl.get("sell_land") else [])
            if sl:
                ss, si = max((z[0], z[1]) for z in sl)
                ks = C.by_mint.get(tr["mint"], [])
                row["no_trade"] = not any((f["slot"], f["idx"]) < (C.rows[k][0], C.rows[k][1]) < (ss, si) and C.rows[k][5] not in WALLETS for k in ks)
        row["q"] = quiet_signals(C, tr["mint"], tr, arm_t, cohort, fbots)
        out.append(row)
    return out


def evaluate(Ws, config):
    fee_rate = sum(w["fail_fee"] for w in Ws) / max(sum(len(w["tries"]) for w in Ws), 1)
    tot = collections.defaultdict(float); removed = []
    for w in Ws:
        v = w["net"] if w["filled"] else 0
        tot["before"] += (v - w["fail_fee"]) / 1e9
        q = w["q"]
        skip = False
        if config == "quiet" and q is not None:
            skip = q["since_last"] >= 1 and q["coh_hold"] == 0 and q["fb_n"] < 2 and q["wh_dump_fol"] < 2.24
        if skip:
            fee_kept = 0; fill_kept = False
        else:
            M = 1 if config == "c5a" else 2
            fee_kept = 0; fill_kept = w["filled"]
            for t in w["tries"]:
                send = True
                if q is not None and t["slot"] >= w["trig"]["slot"] + 6:
                    send = others_seen(G["C"], w["mint"], q["k_trig"], w["trig"]["wallet"], t["pos"]) >= M
                if send: fee_kept += t["fee"]
                if t["fill"]: fill_kept = send
            if w["filled"] and not fill_kept:
                fee_kept += max(w["en_slot"] - w["fill_slot"], 0) * w["k"] * fee_rate
        tot["after"] += ((v if fill_kept else 0) - fee_kept) / 1e9
        tot["fees_saved"] += (w["fail_fee"] - fee_kept) / 1e9
        if w["filled"]:
            tot["fills"] += 1
            if fill_kept: tot["kept"] += 1
            else:
                removed.append(w)
                if v > 0: tot["win_rm"] += 1; tot["win_rm_sol"] += v / 1e9
                else: tot["lose_rm"] += 1; tot["lose_rm_sol"] += v / 1e9
                if w.get("no_trade"): tot["notrade_rm"] += 1
            if w.get("no_trade"): tot["notrade"] += 1
        if skip: tot["skipped"] += 1
    return tot, removed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="append", required=True)
    ap.add_argument("--live"); ap.add_argument("--rec", nargs="*"); ap.add_argument("--config", default="all"); ap.add_argument("--list", action="store_true")
    ap.add_argument("--procs", type=int, default=12)
    A = ap.parse_args()
    cohort = set(json.load(open(COHORT))); fbots = set(json.load(open(FBOTS)))
    recs = A.rec or sorted(glob.glob(f"{COLLECT}/run_*"))
    recs = [d for d in recs if os.path.isdir(f"{d}/txs")]
    configs = ["c5a", "c5", "quiet"] if A.config == "all" else [A.config]
    for run in A.run:
        fn = get_records(run, A.live)
        tmin = tmax = None
        for line in open(fn):
            m = re.search(r'"t":(\d{19})', line)
            if m:
                t = int(m.group(1)) / 1e9
                tmin = t if tmin is None else min(tmin, t); tmax = t if tmax is None else max(tmax, t)
        rows, fails = load_chain((int(tmin - HIST_H * 3600), int(tmax + 600)), recs, A.procs)
        C = ChainIx(rows); G["C"] = C
        Ws = windows(run, fn, C, fails, cohort, fbots)
        nf = sum(1 for w in Ws if w["filled"]); miss = sum(1 for w in Ws if w["q"] is None)
        print(f"\n=== {run}: {fn}\n    windows {len(Ws)}, fills {nf}, trigger not found on the chain recording: {miss} (those are kept as live)")
        if miss > 0.05 * max(len(Ws), 1): print("    WARNING: > 5% of triggers missing on the recording: is the raw recording complete for this run?")
        for cfg in configs:
            t, rem = evaluate(Ws, cfg)
            print(f"  [{cfg:5s}] net {t['before']:+.4f} -> {t['after']:+.4f} SOL ({t['after'] - t['before']:+.4f}) | fills kept {int(t['kept'])}/{int(t['fills'])} | "
                  f"winners removed {int(t['win_rm'])} ({t['win_rm_sol']:+.4f}) | losers removed {int(t['lose_rm'])} ({t['lose_rm_sol']:+.4f}) | "
                  f"no-trade fills removed {int(t['notrade_rm'])}/{int(t['notrade'])} | windows skipped {int(t['skipped'])} | failed-try fees saved {t['fees_saved']:.4f}")
            if A.list:
                for w in rem:
                    print(f"        removed {time.strftime('%m-%d %H:%M:%S', time.gmtime(w['t'] / 1e9 + 18000))} {w['mint']} net {w['net'] / 1e9:+.4f}"
                          f"{' (no-trade)' if w.get('no_trade') else ''}")


if __name__ == "__main__":
    main()
