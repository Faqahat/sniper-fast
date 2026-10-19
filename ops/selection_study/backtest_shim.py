import os
# isolate backtest sim without importing its module-level ROWS/json loads side effects at import-heavy cost
os.environ.setdefault("SLIP","0.08"); os.environ.setdefault("FEE_LEG","0.0008"); os.environ.setdefault("SIZE","2.0")
import sys; sys.path.insert(0,"/root/profit_backtest")
from backtest import simulate
BASE_EXIT={"derisk_frac":0.40,"ride_mult":1.6,"trail_frac":0.85,"cut_r":0.85,"ladder_frac":0.30,"cap_slots":20}
