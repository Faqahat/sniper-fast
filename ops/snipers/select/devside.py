# dev-side wallets per launch: the dev, wallets that buy in the create slot on >= 25% of this dev's launches (its bundle crew),
# and wallets that bought in the create slot and sell in the same slot as the dev's first sell on this launch (co-sellers)
import collections
def build_devside(launches, order):
    freq = collections.defaultdict(collections.Counter); n = collections.Counter()
    for L in launches:
        E = order(L["events"]); n[L["dev"]] += 1
        for u in {e["user"] for e in E if e["buy"] and e["slot"] == L["S"] and e["user"] != L["dev"]}: freq[L["dev"]][u] += 1
    crew = {d: {u for u, c in f.items() if c >= max(3, 0.25 * n[d])} for d, f in freq.items()}
    def side(L, E):
        s = {L["dev"]} | crew.get(L["dev"], set())
        dsell = next((e["slot"] for e in E if e["user"] == L["dev"] and not e["buy"]), None)
        if dsell is not None:
            early = {e["user"] for e in E if e["buy"] and e["slot"] == L["S"]}
            s |= {e["user"] for e in E if (not e["buy"]) and e["slot"] == dsell and e["user"] in early}
        return s
    return side
