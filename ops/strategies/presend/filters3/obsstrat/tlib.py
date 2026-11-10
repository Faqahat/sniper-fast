"""obsstrat tape library: replay our pre-send sell at another decision time on the observatory hold tape.
Tape trade = [slot, idx, j, t_arrival_ns, wallet8, buy(1/0), sol, tok, vsol_post, vtok_post, fl]; our trades carry 'O' in fl.
Sell model: a sell decided at T' lands (arrival clock) at T' + L, L = this position's own measured decision->landing arrival
delay of its real sell. It executes after every other trade that arrived by T'+L (chain order: the latest such trade by
(slot, idx, j)); if that trade is after our real sell in chain order, our real sell is added back to the curve state.
Proceeds = gross curve SOL (tape 'sol' of a sell = vsol_pre * tok / (vtok_pre + tok), checked exact)."""
import json
CUT = 1793516400000000000  # 11-01 12:00 PKT (DEV < CUT <= VAL)
FEE_SELL = 0.0125          # pump sell fee share applied to the change in gross proceeds (approx.)

def load(path="/home/it/sniper-data/filters3/obsstrat/pos_join.jsonl"):
    for line in open(path):
        yield json.loads(line)

class Pos:
    """single buy + single sell positions with a hold tape and a known exit decision time"""
    def __init__(s, d):
        s.d = d; s.ok = False
        h = d.get("h")
        if not h or not h.get("exit") or not h["exit"].get("t"): return
        tr = sorted(h["tr"], key=lambda x: (x[0], x[1], x[2]))
        ob = [x for x in tr if "O" in x[10] and x[5] == 1]; os_ = [x for x in tr if "O" in x[10] and x[5] == 0]
        if len(ob) != 1 or len(os_) != 1: return
        s.tr = tr; s.buy = ob[0]; s.sell = os_[0]
        s.bi = tr.index(s.buy); s.si = tr.index(s.sell)
        s.tok = s.sell[7]; s.act = s.sell[6]
        s.T = h["exit"]["t"]; s.why = h["exit"].get("why")
        s.L = s.sell[3] - s.T
        s.tfill = s.buy[3]
        if s.L < 0 or s.si < s.bi: return
        s.ok = True
    def others_after_fill(s):
        """other wallets' trades that arrived after our fill was seen (engine knows it holds)"""
        return [x for x in s.tr if "O" not in x[10] and x[3] > s.tfill]
    def pre_state_at(s, A):
        """curve state (vsol, vtok) our sell would meet when landing at arrival time A"""
        best = None
        for i, x in enumerate(s.tr):
            if i == s.si: continue
            if x[3] <= A and (best is None or i > best): best = i
        if best is None or best < s.bi:
            best = s.bi  # cannot sell before our own buy is on chain
        x = s.tr[best]; vs, vt = x[8], x[9]
        if best > s.si:  # the real sell is in this state: add it back
            vs += s.sell[6]; vt -= s.sell[7]
        return vs, vt, best
    def proceeds_at(s, Tdec, L=None):
        A = Tdec + (s.L if L is None else L)
        vs, vt, b = s.pre_state_at(A)
        return vs * s.tok / (vt + s.tok), b
    def tape_end_t(s):
        return s.tr[-1][3]
