#!/usr/bin/env python3
"""verify2 core (own code, does not import core/rp.py): load extracted txs, repair the tape, structure, placement, curve replay.
Everything works on x1_extract.py output (raw collector chunks)."""
import json, gzip, os, collections

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "work")
LAUNCH = "/home/moiz/sniper-data/collect/run_20261022_1543/launches.jsonl"
SCORES = "/home/moiz/sniper-data/collect/shadow/scores_v3.jsonl"
PICKS = "/home/moiz/sniper/ops/overnight/core/final2_picks_v3.json"
SLIPF = "/home/moiz/sniper/ops/overnight/core/slip_args.jsonl"
WALLETS = "/home/moiz/sniper/ops/overnight/core/gf_wallets.json"
SLOT_MS = 212.0
PRO_PREFIX = ("9Sh2fd", "DGmspi", "D24ipY", "dKMjeG", "CWiNFA", "9qz7cW", "FiFawH", "AHwJSn", "4yFAz")
VT_DONE = 1_073_000_000_000_000 - 793_100_000_000_000     # virtual tokens when the real token reserves hit 0 (curve complete)

def load_picks():
    return json.load(open(PICKS))

def load_launches(mints):
    S = set(mints); L = {}
    for l in open(LAUNCH):
        try: c = json.loads(l)
        except Exception: continue
        if c["mint"] in S and c["mint"] not in L: L[c["mint"]] = c
    return L

def load_scores(mints):
    S = set(mints); D = {}; O = {}
    for l in open(SCORES):
        try: r = json.loads(l)
        except Exception: continue
        m = r.get("mint")
        if m not in S: continue
        if r.get("type") == "decide": D.setdefault(m, r)
        elif r.get("type") == "obs": O.setdefault(m, r)
    return D, O

def parse_outs(s):
    out = []
    for x in (s or "").split(","):
        p = x.split(":")
        if len(p) >= 4:
            try: out.append((float(p[0]), float(p[1]), p[2] == "1", p[3]))
            except ValueError: pass
    return out

def load_x1():
    return json.load(gzip.open(os.path.join(WORK, "x1_txs.json.gz"), "rt"))

def load_slip():
    S = {}; kinds = collections.Counter()
    for l in open(SLIPF):
        try: r = json.loads(l)
        except Exception: continue
        kinds[r.get("kind")] += 1
        S[r["sig"]] = r
    return S, kinds

def load_wallet_sets():
    W = json.load(open(WALLETS))
    sniper = {u for u, v in W.items() if v[1] >= 5 and v[1] >= 0.5 * v[0]}
    pro = set()
    for p in PRO_PREFIX:
        c = [u for u in W if u.startswith(p)]
        if c: pro.add(max(c, key=lambda u: W[u][0]))
    return pro, sniper

class Mint:
    """one launch: txs in block order (successful trade txs + failed txs), create, glued bundle, (repaired) trade tape.
    repair=True: (1) a tx whose TradeEvents do not explain the bonding curve's token-balance change gets a residual trade
    (missing event inside a recorded tx); (2) a gap between one trade's post-state and the next trade's pre-state (whole
    txs/slots missing from the collector) gets a synthetic net trade right before the next trade."""
    def __init__(self, m, launch, txs, repair=True, empty_slots=None):
        self.m = m; self.c = launch; self.repair = repair
        seen = set(); units = []
        for r in sorted(txs, key=lambda r: (r["s"], r["i"])):
            if r["sig"] in seen: continue
            seen.add(r["sig"]); units.append(r)
        self.units = units
        self.S = launch["slot"]; self.ci = launch["idx"]; bc = launch.get("bonding_curve")
        self.cu = next((u_ for u_, r in enumerate(units) if r["sig"] == launch["sig"]), None)
        self.create_ev = None
        if self.cu is not None:
            for e in units[self.cu]["ev"]:
                if e["kind"] == "C": self.create_ev = e
        tr = []
        self.n_resid = 0; self.n_gap = 0; self.gap_sol = 0.0
        for u_, r in enumerate(units):
            if r["err"]: continue
            evs = [e for e in r["ev"] if e["kind"] == "T"]
            for e in evs:
                tr.append(dict(u=u_, k=e["k"], s=r["s"], i=r["i"], sig=r["sig"], payer=(r["signers"] or [""])[0], user=e["user"], buy=e["buy"] == 1,
                               sol=e["sol"], tok=e["tok"], vsol=e["vsol"], vtok=e["vtok"], fbps=e.get("fee_bps"), cbps=e.get("cfee_bps"), syn=None))
            if repair:
                rows = [x for x in r.get("tb") or [] if x[1] == bc]
                if rows:
                    pre, post = rows[0][2] or 0, rows[0][3] or 0
                    if u_ == self.cu and pre == 0: pre = 1_000_000_000_000_000
                    d_curve = post - pre
                    d_ev = sum((-e["tok"] if e["buy"] == 1 else e["tok"]) for e in evs)
                    if d_curve != d_ev:
                        res = d_curve - d_ev                       # <0 = missing buy (tokens left the curve)
                        last = tr[-1] if (tr and tr[-1]["u"] <= u_) else None
                        if last is not None or self.create_ev:
                            V0, T0 = (last["vsol"], last["vtok"]) if last else (self.create_ev["vsol0"], self.create_ev["vtok0"])
                            T1 = T0 + res; V1 = V0 * T0 // T1      # constant product
                            tr.append(dict(u=u_, k=999, s=r["s"], i=r["i"], sig=r["sig"] + ":resid", payer="?", user="?", buy=res < 0,
                                           sol=abs(V1 - V0), tok=abs(res), vsol=V1, vtok=T1, fbps=None, cbps=None, syn="resid"))
                            self.n_resid += 1
        tr.sort(key=lambda t: (t["u"], t["k"]))
        if repair:
            out = []; prev = (self.create_ev["vsol0"], self.create_ev["vtok0"]) if self.create_ev else None; prev_s = self.S
            for t in tr:
                pre = (t["vsol"] - t["sol"], t["vtok"] + t["tok"]) if t["buy"] else (t["vsol"] + t["sol"], t["vtok"] - t["tok"])
                if t["syn"] == "resid": pre = prev
                if prev is not None and pre != prev and t["syn"] is None:
                    dv = pre[0] - prev[0]; dt = pre[1] - prev[1]
                    # place the synthetic trade in the last empty slot before t (if known), else in t's slot
                    gs = t["s"]
                    if empty_slots:
                        cands = [s for s in range(prev_s + 1, t["s"]) if s in empty_slots]
                        if cands: gs = cands[-1]
                    out.append(dict(u=t["u"], k=-1, s=gs, i=-1, sig="gap:" + t["sig"], payer="?", user="?", buy=dv > 0, sol=abs(dv), tok=abs(dt),
                                    vsol=pre[0], vtok=pre[1], fbps=None, cbps=None, syn="gap"))
                    self.n_gap += 1; self.gap_sol += dv / 1e9
                out.append(t); prev = (t["vsol"], t["vtok"]); prev_s = t["s"]
            tr = out
        self.trades = tr
        # glued bundle: successful buy-only txs at consecutive block indexes right after the create, same slot
        self.glued_units = []
        if self.cu is not None:
            prev = self.ci
            for u_ in range(self.cu + 1, len(units)):
                r = units[u_]
                if r["s"] != self.S or r["i"] != prev + 1: break
                evs = [e for e in r["ev"] if e["kind"] == "T"]
                if r["err"] or not evs or not all(e["buy"] == 1 for e in evs): break
                self.glued_units.append(u_); prev = r["i"]
        self.g_end_u = (self.glued_units[-1] if self.glued_units else self.cu)
        self.post_bundle = self.state_before_unit(self.g_end_u + 1) if self.g_end_u is not None else None
        self.insiders = {launch.get("creator"), launch.get("user")} | {units[u_]["signers"][0] for u_ in self.glued_units}

    def state_before_unit(self, u_):
        """curve state right before tx unit u_ (after every trade in units < u_), excluding synthetic gap trades attached to u_"""
        st = None
        for t in self.trades:
            if t["u"] < u_: st = (t["vsol"], t["vtok"])
            else: break
        if st is None and self.create_ev: st = (self.create_ev["vsol0"], self.create_ev["vtok0"])
        return st

def match_anchors(M, outs, max_slots=8):
    """map each outs entry (ms, sol, isbuy, w6) to a tx unit (after the create+bundle, slots S..S+max_slots) whose fee payer
    (first signer) starts with w6. Successful buys must match the SOL within tolerance; failed txs match any amount;
    isbuy=0 entries (engine: an undecoded touch, never a decoded sell) match any tx of the payer. Returns {unit: ms}."""
    g = M.g_end_u if M.g_end_u is not None else -1
    cand = [u_ for u_ in range(g + 1, len(M.units)) if M.units[u_]["s"] - M.S <= max_slots]
    tsum = collections.defaultdict(lambda: [0, 0, 0])
    for t in M.trades:
        if t["syn"]: continue
        a = tsum[t["u"]]
        if t["buy"]: a[0] += t["sol"]; a[1] += 1
        else: a[2] += 1
    used = set(); seen = {}; miss = []; how = collections.Counter()
    for ms, sol, isbuy, w6 in sorted(outs):
        hit = None
        pay = [u_ for u_ in cand if u_ not in used and (M.units[u_]["signers"] or [""])[0].startswith(w6)]
        if isbuy and sol > 0:
            for u_ in pay:
                if M.units[u_]["err"]: continue
                b = tsum[u_]
                if b[1] and abs(b[0] / 1e9 - sol) <= max(0.02, 0.15 * sol): hit = u_; how["buy_amt"] += 1; break
            if hit is None:
                for u_ in pay:
                    if M.units[u_]["err"]: hit = u_; how["failed"] += 1; break
            if hit is None:
                for u_ in pay:
                    if tsum[u_][1]: hit = u_; how["buy_any_amt"] += 1; break
        else:
            if pay: hit = pay[0]; how["any"] += 1
        if hit is None:
            for u_ in cand:
                if u_ in used: continue
                if any(t["user"].startswith(w6) for t in M.trades if t["u"] == u_ and not t["syn"]): hit = u_; how["user"] += 1; break
        if hit is None: miss.append((ms, sol, isbuy, w6)); how["miss"] += 1; continue
        used.add(hit); seen[hit] = min(ms, seen.get(hit, ms))
    return seen, miss, how

def place(M, seen, land_ms, mode="opt"):
    """our buy goes right AFTER unit `ins`.
    opt : after the last unit (block order) seen before land_ms; every unit before it in block order is ahead too
    pess: also every unseen unit before the first unit seen at/after land_ms is ahead (if one exists)"""
    base = M.g_end_u
    before = [u_ for u_, ms in seen.items() if ms < land_ms]
    after = [u_ for u_, ms in seen.items() if ms >= land_ms]
    ins = max([base] + before)
    if mode == "pess" and after:
        fa = min(after)
        if fa - 1 > ins: ins = fa - 1
    return ins

def replay(M, ins, B=0.5, hold_s=8.0, fill_pen=0.015, over=0.02, sell_cost=0.0005, guard=1.005, fail_cost=0.005, slip=None, drop_buy=None,
           buy_slot_mode="prev", sell_slots=None, fee_mode="event"):
    """our buy right after unit `ins` (synthetic gap trades attached to unit ins+1 come after us). Guard vs the post-bundle price."""
    pre = None
    for t in M.trades:
        if t["u"] <= ins: pre = (t["vsol"], t["vtok"])
        else: break
    if pre is None and M.create_ev: pre = (M.create_ev["vsol0"], M.create_ev["vtok0"])
    if pre is None or M.post_bundle is None: return dict(fill=None, why="nostate")
    V, T = pre; Vb, Tb = M.post_bundle
    ratio = (V / T) / (Vb / Tb)
    if ratio > guard: return dict(fill=False, ratio=ratio, pnl=-fail_cost)
    prev_tr = [t for t in M.trades if t["u"] <= ins and t["fbps"] is not None]
    ft = prev_tr[-1] if prev_tr else next((t for t in M.trades if t["fbps"] is not None), None)
    fr = ((ft["fbps"] + (ft["cbps"] or 0)) / 1e4) if (ft and fee_mode == "event") else 0.0125
    X = int(B * 1e9 / (1 + fr)); q = T * X // (V + X); V += X; T -= q
    q_me = int(q * (1 - fill_pen)); p_in = X / q_me
    nxt = [t for t in M.trades if t["u"] > ins]
    bslot = M.units[ins]["s"] if buy_slot_mode == "prev" else (nxt[0]["s"] if nxt else M.units[ins]["s"])
    ns = sell_slots if sell_slots is not None else int(-(-hold_s * 1000 // SLOT_MS))
    sslot = bslot + ns
    n_after = 0; dropped = 0; slipped = 0; grad = False; last = None; fr_s = fr; n_syn = 0; syn_sol = 0.0
    for t in nxt:
        if t["s"] >= sslot: break
        if t["syn"]: n_syn += 1; syn_sol += (t["sol"] if t["buy"] else -t["sol"]) / 1e9
        if t["buy"]:
            if drop_buy and t["user"] in drop_buy: dropped += 1; continue
            lim = slip.get(t["sig"]) if (slip is not None and not t["syn"]) else None
            if lim is not None and lim.get("kind") == "sol":
                d = T * t["sol"] // (V + t["sol"])
                if d < lim["a2"]: slipped += 1; continue
                V += t["sol"]; T -= d
            elif lim is not None and lim.get("kind") == "tok":
                a1 = lim["a1"]
                if a1 >= T: slipped += 1; continue
                cst = V * a1 // (T - a1) + 1
                if cst * (1 + fr_s) > lim["a2"]: slipped += 1; continue
                V += cst; T -= a1
            else:
                d = T * t["sol"] // (V + t["sol"]); V += t["sol"]; T -= d
            if t["user"] not in M.insiders and not t["syn"]: n_after += 1
        else:
            so = V * t["tok"] // (T + t["tok"]); V -= so; T += t["tok"]
        if t["fbps"] is not None and fee_mode == "event": fr_s = (t["fbps"] + (t["cbps"] or 0)) / 1e4
        last = t
        if T <= VT_DONE: grad = True; break
    so = V * q_me // (T + q_me)
    got = so * (1 - fr_s) / 1e9 - sell_cost
    pnl = got - B * (1 + over)
    return dict(fill=True, ratio=ratio, pnl=pnl, mult=(V / T) / p_in, n_after=n_after, dropped=dropped, slipped=slipped, grad=grad,
                bslot=bslot, sslot=sslot, last_sig=(last["sig"] if last else None), ins_sig=M.units[ins]["sig"], fr=fr, fr_s=fr_s,
                n_syn=n_syn, syn_sol=syn_sol, Vend=V, Tend=T)

def absorbed_units(M, eng, seen, max_slots=1):
    """txs the shadow engine absorbed as 'bundle' by its decision (old_bundle_n - bundle_n in its RACE decide line): the first
    that many buy-like txs (successful buys or failed txs with a buy instruction) after the chain's glued bundle, in block
    order, not matched to an outs entry. They arrived within ~1-3 ms of the create, so they are ahead of any buy of ours."""
    d = (eng or {}).get("decide") or {}
    try: extra = int(d.get("old_bundle_n", 0) or 0) - int(d.get("bundle_n", 0) or 0)
    except ValueError: extra = 0
    if extra <= 0 or M.g_end_u is None: return []
    buyish = set(u for u in range(M.g_end_u + 1, len(M.units)) if M.units[u]["s"] - M.S <= max_slots and (
        (not M.units[u]["err"] and any(t["buy"] and not t["syn"] for t in M.trades if t["u"] == u)) or
        (M.units[u]["err"] and any(x.startswith("Buy") for x in (M.units[u]["ixn"] or [])))))
    out = []
    for u in sorted(buyish):
        if u in seen: continue
        out.append(u)
        if len(out) >= extra: break
    return out

def place2(M, seen, land_ms, mode="opt", absorbed=()):
    ins = place(M, seen, land_ms, mode)
    if absorbed: ins = max(ins, max(absorbed))
    return ins
