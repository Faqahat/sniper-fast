#!/usr/bin/env python3
"""FEE A/B report (engine dip37, --presend-live-fee-ab on) [MEASURED from one run's records, read-only].

Per fee arm (A / B) x leader group (fee = the B clients: fee-ordered leaders; jito = JitoLabs; other):
  attempts      presend_attempt records (dry ones not counted)
  landed        presend_attempt_land with res != unseen; failed = res not ok / unseen, and their fees (lamports charged)
  fills         presend_live_fill records, and fills per 1,000 attempts
  in-slot       landed tries (ok / 6042) in the dump's own slot ("d": the biggest >= 2% sell in the 2 slots before our tx):
                share first after the dump (no trade between the dump and us), median trades between, median tx-index gap
  rivals        4ggJqUDDHB9uZMSyR485VgYLMGLotV7Ctm9NDURCpp6f and DL7cmioGVA7Y4QLnhGZN1zrcNYhqnGzZcrGec3WJJS7d: of our landed tries
                with a BUY of the rival in the same slot (after the dump when the dump is in that slot), how often we were AHEAD
                (lower tx index). dip37 records carry "slot_tr" (the landing slot's trades, FULL addresses: matched exactly);
                older records only the 8-char prefixes in "between" / "after" (marked "prefix")
  money         realized P&L (presend_live_realized), rent back (ok presend_live_ata_close, to the mint's last fill), mSOL per fill
                (realized + rent over the realized positions), failed-try fees, net = realized + rent - failed fees
Records without fee_arm (a run before dip37 or the A/B off) count as arm A; their group comes from "client" and --clients.

usage: feeab_report.py RUN.jsonl [--clients AgaveBam,HarmonicAgave,...] [--json]"""
import argparse
import collections
import json
import statistics
import sys

RIVALS = {"4ggJ": "4ggJqUDDHB9uZMSyR485VgYLMGLotV7Ctm9NDURCpp6f", "DL7": "DL7cmioGVA7Y4QLnhGZN1zrcNYhqnGzZcrGec3WJJS7d"}
assert all(len(v) == 44 for v in RIVALS.values())
CLIENTS = "AgaveBam,HarmonicAgave,HarmonicFiredancer,Firedancer,Agave"
ARMS = ["A", "B"]
GRPS = ["fee", "jito", "other"]


def grp_of(client, clients):
    return "fee" if client in clients else "jito" if client == "JitoLabs" else "other"


class Cell:
    def __init__(self):
        self.att = self.landed = self.failed = self.fail_fees = self.unseen = self.fills = 0
        self.pnl = self.rent = self.npos = self.wins = 0
        self.dslot = 0          # landed ok / 6042 tries in the dump's slot
        self.first = 0          # ... first after the dump
        self.between = []       # ... trades between the dump and us
        self.gap = []           # ... our tx index - the dump's
        self.riv = {k: [0, 0, 0] for k in RIVALS}   # co-slot landings, we ahead, prefix-matched (old records)

    def add(self, o):
        for k in ("att", "landed", "failed", "fail_fees", "unseen", "fills", "pnl", "rent", "npos", "wins", "dslot", "first"):
            setattr(self, k, getattr(self, k) + getattr(o, k))
        self.between += o.between
        self.gap += o.gap
        for k in RIVALS:
            self.riv[k] = [a + b for a, b in zip(self.riv[k], o.riv[k])]

    def net(self):
        return self.pnl + self.rent - self.fail_fees

    def json(self):
        med = lambda v: statistics.median(v) if v else None
        return {"attempts": self.att, "landed": self.landed, "failed": self.failed, "failed_fees": self.fail_fees, "unseen": self.unseen,
                "fills": self.fills, "fills_per_1k": self.fills * 1000 / self.att if self.att else None,
                "dump_slot_landed": self.dslot, "first_after_dump": self.first, "between_p50": med(self.between), "idx_gap_p50": med(self.gap),
                "rivals": {k: {"co_slot": v[0], "we_ahead": v[1], "prefix_matched": v[2]} for k, v in self.riv.items()},
                "positions": self.npos, "wins": self.wins, "realized": self.pnl, "rent": self.rent,
                "msol_per_fill": (self.pnl + self.rent) / self.npos / 1e6 if self.npos else None, "net": self.net()}


def rivals_in_slot(r, our_idx, dump_idx):
    """{rival: (ahead, prefix)} for the rivals with a buy in our landing slot (after the dump when it is in that slot)"""
    out = {}
    slot = r.get("slot")
    if isinstance(r.get("slot_tr"), list):
        for e in r["slot_tr"]:
            idx, user, buy = e[0], e[2], e[3]
            if not buy or idx == our_idx or (dump_idx is not None and idx <= dump_idx):
                continue
            for k, full in RIVALS.items():
                if user == full and k not in out:
                    out[k] = (idx < our_idx, False)
        return out
    for lst, ahead in (("between", True), ("after", False)):
        for t in r.get(lst) or []:
            if not t.get("buy") or t.get("slot") != slot:
                continue
            for k, full in RIVALS.items():
                if t.get("user") == full[:8] and k not in out:
                    out[k] = (ahead, True)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run")
    ap.add_argument("--clients", default=None, help="the B clients (default: the run's fee_ab.clients, else " + CLIENTS + ")")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    cells = collections.defaultdict(Cell)
    win_cell = {}            # window -> (arm, grp) of its fill
    mint_cell = {}           # mint -> (arm, grp) of its last fill
    clients = set((a.clients or CLIENTS).split(","))
    cfg, has_arm, n_rec = None, False, 0
    for line in open(a.run):
        if '"presend_' not in line and '"run_start"' not in line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        ev = r.get("ev")
        if ev == "run_start":
            fa = (r.get("presend_live") or {}).get("fee_ab")
            if fa:
                cfg = fa
                if not a.clients:
                    clients = set(fa.get("clients") or CLIENTS.split(","))
            continue
        if ev not in ("presend_attempt", "presend_attempt_land", "presend_live_fill", "presend_live_realized", "presend_live_ata_close"):
            continue
        n_rec += 1
        arm = r.get("fee_arm")
        has_arm |= arm is not None
        key = (arm or "A", r.get("fee_grp") or grp_of(r.get("client", ""), clients))
        if ev == "presend_attempt":
            if not r.get("dry"):
                cells[key].att += 1
        elif ev == "presend_attempt_land":
            c = cells[key]
            res = r.get("res")
            if res == "unseen":
                c.unseen += 1
                continue
            c.landed += 1
            if res != "ok":
                c.failed += 1
                c.fail_fees += r.get("fee") or 0
            if res not in ("ok", "6042") or r.get("idx") is None:
                continue
            d = r.get("d") or {}
            dump_idx = d.get("idx") if d.get("slot") == r.get("slot") else None
            if dump_idx is not None:
                c.dslot += 1
                nb = r.get("n_between") or 0
                c.first += nb == 0
                c.between.append(nb)
                c.gap.append(r["idx"] - dump_idx)
            for k, (ahead, pref) in rivals_in_slot(r, r["idx"], dump_idx).items():
                c.riv[k][0] += 1
                c.riv[k][1] += ahead
                c.riv[k][2] += pref
        elif ev == "presend_live_fill":
            cells[key].fills += 1
            win_cell[r.get("w")] = key
            mint_cell[r.get("mint")] = key
        elif ev == "presend_live_realized":
            k2 = key if arm is not None else win_cell.get(r.get("w"), key)
            c = cells[k2]
            p = r.get("pnl")
            if p is not None:
                c.npos += 1
                c.pnl += p
                c.wins += p > 0
        elif ev == "presend_live_ata_close":
            if r.get("ok") and r.get("mint") in mint_cell:
                cells[mint_cell[r["mint"]]].rent += r.get("delta") or 0
    arms = sorted({k[0] for k in cells}, key=lambda x: (x not in ARMS, x))
    out = {"run": a.run, "fee_ab": cfg, "clients": sorted(clients), "fee_arm_in_records": has_arm, "cells": {}, "arms": {}}
    for arm in arms:
        tot = Cell()
        for g in sorted({k[1] for k in cells if k[0] == arm}, key=lambda x: (x not in GRPS, GRPS.index(x) if x in GRPS else x)):
            out["cells"][f"{arm}/{g}"] = cells[(arm, g)].json()
            tot.add(cells[(arm, g)])
        out["arms"][arm] = tot.json()
    if a.json:
        json.dump(out, sys.stdout, indent=1)
        print()
        return
    print(f"FEE A/B report: {a.run}")
    print(f"  config: {json.dumps(cfg) if cfg else 'no fee_ab in run_start (A/B off or a run before dip37)'}; B clients {','.join(sorted(clients))}")
    if not has_arm:
        print("  NOTE: no record carries fee_arm: every row is arm A (a baseline)")
    hdr = ["arm/grp", "att", "landed", "failed", "fees mSOL", "fills", "/1k", "dumpslot", "1st%", "btw p50", "gap p50", "4ggJ ahead", "DL7 ahead",
           "pos", "win%", "realized", "rent", "mSOL/fill", "net mSOL"]

    def row(name, j):
        pct = lambda n, d: f"{100 * n / d:.0f}%" if d else "-"
        f = lambda x, p=2: "-" if x is None else f"{x:.{p}f}"
        rv = lambda k: f"{j['rivals'][k]['we_ahead']}/{j['rivals'][k]['co_slot']}" + ("p" if j['rivals'][k]['prefix_matched'] else "")
        return [name, j["attempts"], j["landed"], j["failed"], f(j["failed_fees"] / 1e6), j["fills"], f(j["fills_per_1k"]), j["dump_slot_landed"],
                pct(j["first_after_dump"], j["dump_slot_landed"]), f(j["between_p50"], 1), f(j["idx_gap_p50"], 0), rv("4ggJ"), rv("DL7"),
                j["positions"], pct(j["wins"], j["positions"]), f(j["realized"] / 1e6), f(j["rent"] / 1e6), f(j["msol_per_fill"]), f(j["net"] / 1e6)]

    rows = [hdr]
    for arm in arms:
        for k, j in out["cells"].items():
            if k.split("/")[0] == arm:
                rows.append(row(k, j))
        rows.append(row(f"{arm} all", out["arms"][arm]))
    w = [max(len(str(r[i])) for r in rows) for i in range(len(hdr))]
    for r in rows:
        print("  " + "  ".join(str(x).rjust(w[i]) if i else str(x).ljust(w[i]) for i, x in enumerate(r)))
    print("  rivals 'a/n': we were ahead of the rival in n of our landed tries where it bought in the same slot (after the dump); 'p' = some "
          "matched by 8-char prefix (records before dip37)")
    print("  money in mSOL; net = realized + rent back - failed-try fees; mSOL/fill over the realized positions")


if __name__ == "__main__":
    main()
