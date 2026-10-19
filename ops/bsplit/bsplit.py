# READ-ONLY: classify each overnight blacklist paper token as creator-bundled or not (glued buys right after the create,
# same method as /root/indep), and record the post-bundle price vs floor. Output: /root/bsplit/out.jsonl
import sys, re, json, threading, concurrent.futures as cf
sys.path.insert(0, "/root/indep")
from common import get_block, is_vote, events, tx_summary, load_tipmap, VSOL0

LOG = "/root/arbx-fast/paper_blnight.log"
tipmap = load_tipmap()
launch = {}
for l in open(LOG):
    m = re.search(r"PAPER launch #\d+ slot=(\d+) mint=(\w+) dev_buy=(\d+)", l)
    if m:
        launch[m.group(2)] = (int(m.group(1)), int(m.group(3)))
done = {}
for l in open(LOG):
    m = re.search(r"PAPER done mint=(\w+) .*?peak_r=([\d.]+) .*?@1\.00=([+-][\d.]+)", l)
    if m and m.group(1) in launch:
        done[m.group(1)] = (float(m.group(2)), float(m.group(3)))
mints = [m for m in done]
print("paper done:", len(mints), file=sys.stderr)

out = open("/root/bsplit/out.jsonl", "w")
lock = threading.Lock()


def work(mint):
    slot, dev = launch[mint]
    peak, pnl1 = done[mint]
    blk = get_block(slot)
    rec = {"mint": mint, "slot": slot, "dev": dev, "peak": peak, "pnl1": pnl1}
    if not isinstance(blk, dict) or "transactions" not in blk:
        rec["missing"] = True
    else:
        txs = blk["transactions"]
        cidx = None
        for i, t in enumerate(txs):
            meta = t.get("meta") or {}
            if meta.get("err") is not None:
                continue
            tr, cr = events(meta.get("logMessages"))
            if any(c["mint"] == mint for c in cr):
                cidx = i
                base = next((e["vsol"] for e in tr if e["mint"] == mint and e["buy"]), VSOL0 + dev)
                creator_signers = set(tx_summary(t, tipmap)[0]["signers"])
                break
        if cidx is None:
            rec["nocreate"] = True
        else:
            glued, gsol, gv, run_open = 0, 0, base, True
            same_buys, same_sol, last_v, first_ind = 0, 0, base, None
            d = 0
            for t in txs[cidx + 1:]:
                if is_vote(t):
                    continue
                d += 1
                meta = t.get("meta") or {}
                tr, _ = events(meta.get("logMessages"))
                ev = [e for e in tr if e["mint"] == mint and e["buy"]]
                if run_open:
                    if ev and meta.get("err") is None:
                        glued += 1
                        gsol += sum(e["sol"] for e in ev)
                        gv = ev[-1]["vsol"]
                    else:
                        run_open = False
                if ev and meta.get("err") is None:
                    same_buys += 1
                    same_sol += sum(e["sol"] for e in ev)
                    last_v = ev[-1]["vsol"]
                    if not run_open and first_ind is None and glued >= 0 and d > glued:
                        e0 = ev[0]
                        if e0["tok"] > 0:
                            fl = base ** 2 / (VSOL0 * 1_073_000_000_000_000)
                            first_ind = (e0["sol"] / e0["tok"]) / fl
            rec.update(glued=glued, gsol=gsol / 1e9, bmult=(gv / base) ** 2, same_buys=same_buys, same_sol=same_sol / 1e9,
                       slot_end_mult=(last_v / base) ** 2, first_ind=first_ind, creator_tip=bool(tx_summary(txs[cidx], tipmap)[0]["tips"]))
    with lock:
        out.write(json.dumps(rec) + "\n")
        out.flush()


with cf.ThreadPoolExecutor(max_workers=8) as ex:
    list(ex.map(work, mints))
print("BSPLIT_DONE", file=sys.stderr)
