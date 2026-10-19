import json
from urllib.parse import urlparse
POSM = json.load(open("/root/sel2/pos_meta.json")); NEGM = json.load(open("/root/sel2/neg_meta.json"))
POSF = json.load(open("/root/sel/pos_feat.json")); NEGF = json.load(open("/root/sel/neg_feat.json"))
BS = json.load(open("/root/sel/pos.json"))["buyslot"]


def host(u):
    try:
        return urlparse(u).netloc.lower() or "?"
    except Exception:
        return "?"


def build(md, fd, y, fb=None):
    fb = fb or {}; r = []
    for m, v in md.items():
        if v.get("status") not in ("ok", "no_uri_json") or not v.get("uri"):
            continue
        s = fd.get(m, {}).get("create_slot") or fb.get(m)
        if not s:
            continue
        r.append({"y": y, "slot": s, "h": v.get("uri_host") or host(v["uri"])})
    return r


pos = build(POSM, POSF, 1, BS); neg = build(NEGM, NEGF, 0)
ps = sorted(x["slot"] for x in pos); lo, hi = ps[0], ps[-1]
neg = [x for x in neg if lo <= x["slot"] <= hi]
rows = sorted(pos + neg, key=lambda x: x["slot"])
cut = int(len(rows) * 0.6); ss = rows[cut]["slot"]
tr = [x for x in rows if x["slot"] < ss]; te = [x for x in rows if x["slot"] >= ss]
PREF = {"ipfs.io", "metadata.j7tracker.io", "m.rapidlaunch.io", "gateway.pinata.cloud"}
AVOID = {"gg.sc", "ipfs.launchblitz.ai", "pf.jake-98f.workers.dev", "ipfs2.extraction.live",
         "answering-afterwards-spoke-communication.trycloudflare.com", "fast-ipfs.com",
         "storage.googleapis.com", "meta.mwmwmwmwmwmwmwmwmw.uk", "img.launchtracker4444.com",
         "meta.uxento.io", "gatewaypinata.online"}


def ev(rows, fn, nm):
    P = sum(x["y"] for x in rows); sel = [x for x in rows if fn(x)]
    if not sel:
        print(f"    {nm}: sel 0"); return
    tp = sum(x["y"] for x in sel); b = P / len(rows)
    print(f"    {nm:12s} sel={len(sel):4d} tp={tp:3d} prec={tp/len(sel):.3f} recall={tp/P:.3f} lift={(tp/len(sel))/b:.2f}")


for nm, fn in [("PREFERRED-host (ipfs.io/j7tracker/rapidlaunch/pinata)", lambda x: x["h"] in PREF),
               ("NOT-in-AVOID (blacklist of bundler-bot launchers)", lambda x: x["h"] not in AVOID),
               ("ipfs.io only (official pump UI)", lambda x: x["h"] == "ipfs.io")]:
    print(nm)
    ev(tr, fn, "TRAIN"); ev(te, fn, "TEST")
trp = sum(x["y"] for x in tr); tep = sum(x["y"] for x in te)
print(f"\ntrain pos={trp}/{len(tr)} base={trp/len(tr):.3f} | test pos={tep}/{len(te)} base={tep/len(te):.3f}")
print(f"full: pos={len(pos)} neg={len(neg)} base={len(pos)/(len(pos)+len(neg)):.3f}")
