#!/usr/bin/env python3
"""CASEBOOK ledger helper. ledger.json = {"meta":..., "tokens":[...], "H":{hid:{text,cat,sup:[],con:[],unt:[],status,notes}}}
usage: ledger.py init | ledger.py show  (writes ledger.txt)
Hypotheses are also updated from python via load()/save()/mark()."""
import json, sys, os, datetime
P = "/home/moiz/sniper/ops/strategies/rivals/9pQQ/casebook/ledger.json"
T = "/home/moiz/sniper/ops/strategies/rivals/9pQQ/casebook/ledger.txt"
def load(): return json.load(open(P))
def save(L):
    L["meta"]["updated"] = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    json.dump(L, open(P + ".tmp", "w"), indent=1); os.replace(P + ".tmp", P); write_txt(L)
def add(L, hid, text, cat, notes="", status="open", src=""):
    if hid not in L["H"]: L["H"][hid] = dict(text=text, cat=cat, sup=[], con=[], unt=[], status=status, notes=notes, src=src)
def mark(L, hid, tok, v, note=None):
    h = L["H"][hid]
    for k in ("sup", "con", "unt"):
        if tok in h[k]: h[k].remove(tok)
    h[{"s": "sup", "c": "con", "u": "unt"}[v]].append(tok)
    if note: h["notes"] = (h["notes"] + " | " if h["notes"] else "") + f"{tok}: {note}"
def write_txt(L):
    with open(T, "w") as f:
        f.write(f"9pQQ CASEBOOK LEDGER  (updated {L['meta'].get('updated')})  tokens studied: {len(L['tokens'])}\n")
        f.write("status: strong / open / killed / hard(=held on every trade).  sup/con/unt = tokens supporting / contradicting / not testing\n\n")
        for cat in ("buy", "sell", "skip", "meta"):
            f.write(f"===== {cat.upper()} =====\n")
            for hid, h in L["H"].items():
                if h["cat"] != cat: continue
                f.write(f"[{hid}] ({h['status']}) sup {len(h['sup'])} / con {len(h['con'])} / unt {len(h['unt'])}  {h['text']}\n")
                if h.get("notes"): f.write(f"      notes: {h['notes'][-900:]}\n")
            f.write("\n")
        f.write("tokens: " + ", ".join(L["tokens"]) + "\n")
if __name__ == "__main__":
    if sys.argv[1] == "init" and not os.path.exists(P):
        L = dict(meta={}, tokens=[], H={})
        save(L)
    write_txt(load())
