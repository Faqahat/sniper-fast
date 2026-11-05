"""TAIL shared helpers: load positions, DEV/VAL split, per-run tables."""
import json, collections
T = "/home/moiz/sniper-data/filters3/tail"
SPLIT = 1793516400000000000  # 11-01 12:00 PKT (record clock t, ns)
OURS = {"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR", "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"}
RUNS = [37, 38, 39, 40, 41, 42]
def load():
    out = []
    for r in RUNS:
        for l in open(f"{T}/pos_r{r}.jsonl"):
            d = json.loads(l); d["run"] = r
            d["set"] = "VAL" if (r == 42 and d["t"] >= SPLIT) else "DEV"
            d["rk"] = f"r{r}" if r != 42 else ("r42a" if d["set"] == "DEV" else "r42b")
            out.append(d)
    out.sort(key=lambda d: d["t"])
    return out
def kind(d): return (d.get("arm") or {}).get("kind") or "t2"
