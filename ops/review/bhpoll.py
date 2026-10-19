# REVIEW: poll getLatestBlockhash(confirmed) every 200 ms; print "t_ns blockhash" (to age the dumped txs' blockhashes)
import sys, time, json
sys.path.insert(0, "/root/indep")
from common import rpc
end = time.time() + float(sys.argv[1])
while time.time() < end:
    r = rpc("getLatestBlockhash", [{"commitment": "confirmed"}], tries=1, timeout=5)
    if isinstance(r, dict) and "value" in r:
        print(time.time_ns(), r["value"]["blockhash"], flush=True)
    time.sleep(0.2)
