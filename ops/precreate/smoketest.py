import os, sys, json, time
sys.path.insert(0, "/root/profit_backtest")
sys.path.insert(0, "/root/precreate")
import extract_precreate as E
S = json.load(open("/root/precreate/sample.json"))
import random; random.seed(1)
sub = random.sample(S, 20)
t0=time.time()
for r in sub:
    o = E.extract_one(r)
    print(o.get("is_his"), "fund_found", o.get("fund_found"), "recency", o.get("fund_recency_slots"),
          "amt", round(o["fund_amount"],4) if o.get("fund_amount") else None,
          "prior_n", o.get("prior_n"), "csig", o.get("create_sig_found"), o.get("err",""))
print("elapsed %.1fs for 20 (serial)" % (time.time()-t0))
