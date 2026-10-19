# READ-ONLY helpers shared by the race scripts: on-chain record builders (block S, S+1..S+8) and race labels.
import sys, json, collections, base64
sys.path.insert(0, "/root/det/lib")
from common import events, tx_summary, load_tipmap, is_vote, b58enc, CREATE_DISC, VSOL0
sys.path.insert(0, "/root/det/lib")
from nrpc import rpc

W = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
OURS = {"FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS"}   # our own sniper wallet: never an outsider
T22 = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
_tipmap = None


def tipmap():
    global _tipmap
    if _tipmap is None:
        _tipmap = load_tipmap()
    return _tipmap


def parse_create_full(raw):
    o = 8
    strs = []
    for _ in range(3):
        n = int.from_bytes(raw[o:o + 4], "little"); o += 4
        strs.append(raw[o:o + n].decode("utf8", "replace")); o += n
    mint = b58enc(raw[o:o + 32]); o += 32
    o += 32
    user = b58enc(raw[o:o + 32]); o += 32
    creator = b58enc(raw[o:o + 32]) if len(raw) >= o + 32 else user
    return dict(name=strs[0][:60], symbol=strs[1][:30], uri=strs[2][:300], mint=mint, user=user, creator=creator)


def block_record(S, mint):
    """same record as /root/det/lib/blk_fixed.py for one mint in block S (create tx + every later tx on the mint in S)."""
    blk = rpc("getBlock", [S, {"encoding": "json", "maxSupportedTransactionVersion": 1, "transactionDetails": "full",
                               "rewards": False, "commitment": "confirmed"}], timeout=120)
    if not isinstance(blk, dict) or "transactions" not in blk:
        return {"mint": mint, "slot": S, "missing": "block"}
    txs = blk["transactions"]
    nvl, nv = [], -1
    for t in txs:
        if is_vote(t):
            nvl.append(None)
        else:
            nv += 1
            nvl.append(nv)
    for idx, t in enumerate(txs):
        if nvl[idx] is None:
            continue
        meta = t.get("meta") or {}
        if meta.get("err") is not None:
            continue
        logs = meta.get("logMessages") or []
        if not any("Instruction: Create" in l for l in logs):
            continue
        cr = []
        for l in logs:
            if l.startswith("Program data: "):
                try:
                    raw = base64.b64decode(l[14:] + "===")
                except Exception:
                    continue
                if raw[:8] == CREATE_DISC:
                    try:
                        cr.append(parse_create_full(raw))
                    except Exception:
                        pass
        c = [x for x in cr if x["mint"] == mint]
        if not c:
            continue
        c = c[0]
        s, keys = tx_summary(t, tipmap())
        tr, _ = events(logs)
        cev = [e for e in tr if e["mint"] == mint]
        dev = sum(e["sol"] for e in cev if e["buy"])
        base = cev[-1]["vsol"] if cev else VSOL0
        ins = [l for l in logs if l.startswith("Program log: Instruction: ")]
        rec = {"mint": mint, "slot": S, "bt": blk.get("blockTime"), "ntx": len(txs), "nnv": nv + 1, "csig": t["transaction"]["signatures"][0],
               "cidx": idx, "cnv": nvl[idx], "name": c["name"], "symbol": c["symbol"], "uri": c["uri"], "creator": c["creator"], "user": c["user"],
               "payer": s["payer"], "signers": s["signers"], "cu_price": s["cu_price"], "cu_limit": s["cu_limit"], "fee": s["fee"],
               "tips": s["tips"], "keytip": s["keytip"], "progs": s["progs"], "ins": [l[26:40] for l in ins][:12], "t22": T22 in keys,
               "nkeys": len(keys), "dev": dev, "base": base, "ver": t.get("version")}
        glued, gsol, gv, run_open, later = 0, 0, base, True, []
        for j in range(idx + 1, len(txs)):
            if nvl[j] is None:
                continue
            tt = txs[j]
            m2 = tt.get("meta") or {}
            ok = m2.get("err") is None
            tr2, _ = events(m2.get("logMessages")) if ok else ([], [])
            ev = [e for e in tr2 if e["mint"] == mint]
            evb = [e for e in ev if e["buy"]]
            if run_open:
                if evb and ok:
                    glued += 1
                    gsol += sum(e["sol"] for e in evb)
                    gv = evb[-1]["vsol"]
                else:
                    run_open = False
            touch = False
            if not ev:
                msg = tt["transaction"]["message"]
                if mint in msg["accountKeys"] or mint in (m2.get("loadedAddresses") or {}).get("writable", []):
                    touch = True
            if ev or touch:
                s2, _ = tx_summary(tt, tipmap())
                later.append({"d": nvl[j] - nvl[idx], "sig": s2["sig"][:20], "payer": s2["payer"], "ok": ok,
                              "ev": [[e["buy"], e["user"], e["sol"], e["tok"], e["vsol"]] for e in ev], "cu_price": s2["cu_price"],
                              "tips": [[x[0], x[1]] for x in s2["tips"]], "glued": run_open and bool(evb) and ok, "his": W in s2["signers"]})
        rec.update(glued=glued, gsol=gsol, gv=gv, later=later[:400], nlater=len(later))
        return rec
    return {"mint": mint, "slot": S, "missing": "create_not_in_block"}


def s1_record(mint, csig, S, win=8, fetch_to=5, cap=90):
    """every sig on the mint in S..S+win; getTransaction for OK txs in S+1..S+fetch_to (same as race_collect.py)."""
    anchor = None
    for k in range(win + 1, win + 6):
        b = rpc("getBlock", [S + k, {"encoding": "json", "maxSupportedTransactionVersion": 1, "transactionDetails": "signatures",
                                     "rewards": False, "commitment": "confirmed"}], timeout=60)
        if isinstance(b, dict) and b.get("signatures"):
            anchor = b["signatures"][0]
            break
    rec = {"mint": mint, "slot": S}
    sigs, pages, before = [], 0, anchor
    while True:
        prm = {"limit": 1000, "until": csig}
        if before:
            prm["before"] = before
        r = rpc("getSignaturesForAddress", [mint, prm], tries=10)
        pages += 1
        if not isinstance(r, list):
            rec["sig_err"] = str(r)[:100]
            return rec
        sigs += r
        if len(r) < 1000 or pages >= 6:
            break
        before = r[-1]["signature"]
    sigs = [x for x in reversed(sigs) if S <= x["slot"] <= S + win]
    rec["act"] = sorted(collections.Counter(x["slot"] - S for x in sigs if x.get("err") is None).items())
    rec["act_err"] = sorted(collections.Counter(x["slot"] - S for x in sigs if x.get("err") is not None).items())
    pick = [x for x in sigs if x.get("err") is None and 1 <= x["slot"] - S <= fetch_to]
    rec["n_pick"] = len(pick)
    rows = []
    for x in pick[:cap]:
        tx = rpc("getTransaction", [x["signature"], {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}])
        if not isinstance(tx, dict) or "meta" not in tx:
            rows.append({"d": x["slot"] - S, "miss": 1})
            continue
        s, _ = tx_summary(tx, tipmap())
        tr, _ = events((tx.get("meta") or {}).get("logMessages"))
        rows.append({"d": x["slot"] - S, "sig": x["signature"][:16], "payer": s["payer"], "nsig": len(s["signers"]), "fee": s["fee"],
                     "cu_price": s["cu_price"], "tips": [[a[0], a[1]] for a in s["tips"]], "bt": tx.get("blockTime"),
                     "ev": [[e["buy"], e["user"], e["sol"], e["tok"], e["vsol"]] for e in tr if e["mint"] == mint]})
    rec["rows"] = rows
    return rec


def labels(b, s, pros=frozenset(), min_buy=0.0):
    """race labels from a block record b (slot S) and an s1 record s (S+1..S+5).
    outsider = OK buy tx whose payer/buyers are not the creator, the create payer/signers or a glued-bundle wallet.
    A glued tx from a known multi-creator sniper wallet ('pros') counts as an outsider (fast sniper right behind the create).
    4yFAz is reported separately: *_x = excluding him."""
    creator, user = b["creator"], b["user"]
    later = b.get("later") or []
    cset = {creator, user, b.get("payer")} | set(b.get("signers") or []) | OURS
    glued_out = set()
    broken = False   # a creator bundle is atomic + contiguous: once a known sniper sits in the run, the rest is not bundle
    for x in later:
        if x.get("glued"):
            if broken or x["payer"] in pros or x.get("his"):
                broken = True
                glued_out.add(x["sig"])
            else:
                cset.add(x["payer"])
                for e in x["ev"]:
                    cset.add(e[1])
    o = {}
    outS, errS = [], 0
    for x in later:
        if not x.get("ok"):
            errS += 1
            continue
        if x.get("glued") and x["sig"] not in glued_out:
            continue
        evb = [e for e in x["ev"] if e[0]]
        if not evb:
            continue
        if x["payer"] in cset or {e[1] for e in evb} <= cset:
            continue
        sol = sum(e[2] for e in evb) / 1e9
        if sol < min_buy:
            continue
        outS.append((x["d"], x["payer"], sol, x.get("cu_price") or 0, sum(t[1] for t in x.get("tips") or []) / 1e9, bool(x.get("his") or any(e[1] == W for e in evb))))
    per, perx = collections.defaultdict(set), collections.defaultdict(set)
    sol_by, sol_byx = collections.Counter(), collections.Counter()
    for x in (s or {}).get("rows", []):
        if "ev" not in x:
            continue
        evb = [e for e in x["ev"] if e[0]]
        if not evb or x["payer"] in cset or {e[1] for e in evb} <= cset:
            continue
        sol = sum(e[2] for e in evb) / 1e9
        if sol < min_buy:
            continue
        per[x["d"]].add(x["payer"])
        sol_by[x["d"]] += sol
        if x["payer"] != W and all(e[1] != W for e in evb):
            perx[x["d"]].add(x["payer"])
            sol_byx[x["d"]] += sol
    pS = {p for _, p, *_ in outS}
    pSx = {p for _, p, _, _, _, h in outS if not h}
    o["errS"] = errS
    o["outS_n"], o["outS_nx"] = len(pS), len(pSx)
    o["outS_sol"] = sum(x[2] for x in outS)
    o["outS_solx"] = sum(x[2] for x in outS if not x[5])
    o["outS1_n"] = len(per[1])
    o["out01_n"], o["out01_nx"] = len(pS | per[1]), len(pSx | perx[1])
    o["out2s_n"] = len(pS.union(*[per[k] for k in range(1, 6)]))
    o["out2s_nx"] = len(pSx.union(*[perx[k] for k in range(1, 6)]))
    o["out01_sol"] = o["outS_sol"] + sol_by[1]
    o["out2s_sol"] = o["outS_sol"] + sum(sol_by[k] for k in range(1, 6))
    o["out2s_solx"] = o["outS_solx"] + sum(sol_byx[k] for k in range(1, 6))
    o["outS_d"] = [x[0] for x in outS][:80]
    o["outS_cu"] = [x[3] for x in outS][:80]
    o["outS_tip"] = [x[4] for x in outS][:80]
    o["outS_sv"] = [round(x[2], 4) for x in outS][:80]
    o["outS_his"] = [x[5] for x in outS][:80]
    o["glued_pro"] = len(glued_out)
    return o


def path_pts(b, s, prows=None, S=None):
    """(t_ms, vsol) chronological: S from the block (d * ms_per_tx), S+1..S+5 every trade, then sampled later rows."""
    nnv = b.get("nnv") or 1000
    mpt = 400.0 / max(nnv, 1)
    pts = [(0.0, b.get("base") or VSOL0)]
    for x in b.get("later") or []:
        if x.get("ok") and x["ev"]:
            pts.append((x["d"] * mpt, x["ev"][-1][4]))
    seq = collections.defaultdict(list)
    for x in (s or {}).get("rows", []):
        if "ev" in x:
            seq[x["d"]].append(x)
    for d in sorted(seq):
        rows = seq[d]
        for i, x in enumerate(rows):
            if x["ev"]:
                pts.append((d * 400.0 + 400.0 * i / max(len(rows), 1), x["ev"][-1][4]))
    capped = (s or {}).get("n_pick", 0) > len((s or {}).get("rows", []))
    for row in prows or []:
        if len(row) < 2 or not row[1]:
            continue
        d = row[0] - S
        if d <= 5 and not capped:
            continue
        pts.append((d * 400.0 + 399.0, row[1][-1][4]))
    pts.sort(key=lambda z: z[0])
    return [[round(t), v] for t, v in pts], mpt
