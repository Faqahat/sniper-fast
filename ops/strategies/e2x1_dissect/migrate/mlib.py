"""migrate agent: shared paths/constants; reuses grad's tape (glib.Tape)."""
import sys, os
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/grad")
from glib import Tape, last_before, q_eff, pool_state_after, pool_fee, pkt, pday, G, SLOT_MS, PKT   # noqa
D = "/home/moiz/sniper-data/e2x1_dissect/migrate"
SCR = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/e2x1_migrate"
os.makedirs(D, exist_ok=True); os.makedirs(SCR, exist_ok=True)
TRAIN = ["10-24", "10-25", "10-26"]; TEST = ["10-27", "10-28"]
SLOT_S = SLOT_MS / 1000.0
