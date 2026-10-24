import json, math
def load(p):
    M = json.load(open(p))
    def score(x):
        f = M["F0"]; bins = []
        for k, e in zip(M["features"], M["edges"]):
            if "==" in k: a, v = k.split("==", 1); val = 1.0 if str(x.get(a)) == v else 0.0
            else:
                v = x.get(k); val = float(v) if isinstance(v, (int, float)) and v is not None and not (isinstance(v, float) and math.isnan(v)) else float("nan")
            if math.isnan(val): bins.append(0); continue
            lo, hi = 0, len(e)
            while lo < hi:
                mid = (lo + hi) // 2
                if e[mid] <= val: lo = mid + 1
                else: hi = mid
            bins.append(lo + 1)
        for t in M["trees"]:
            n = t
            while "w" not in n: n = n["l"] if bins[n["f"]] <= n["b"] else n["r"]
            f += M["lr"] * n["w"]
        return f
    return M, score
