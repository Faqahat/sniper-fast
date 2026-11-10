"""shared helpers for YOUNG."""
import json, pickle, datetime
D = "/home/it/sniper-data/presend_young"
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
FEE = 0.0125
def load():
    T = json.load(open(f"{D}/trig.json")); tp = pickle.load(open(f"{D}/tapes.pkl", "rb"))
    return T["meta"], T["rows"], tp
def pkt(t_ns): return datetime.datetime.utcfromtimestamp(t_ns / 1e9) + datetime.timedelta(hours=5)
CUT = datetime.datetime(2026, 10, 28, 0, 0)  # PKT train/test cut
def is_test(r): return pkt(r["t"]) >= CUT
def price(vs, vt): return vs / vt
def buy_out(vs, vt, sol):  # tokens for sol in (gross), fee taken from input
    net = sol * (1 - FEE); return vt * net / (vs + net), vs + net, vt - vt * net / (vs + net)
def sell_out(vs, vt, tok):  # sol out net of fee
    g = vs * tok / (vt + tok); return g * (1 - FEE), vs - g, vt + tok
