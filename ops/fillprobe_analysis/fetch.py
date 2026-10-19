import json, os, sys, urllib.request, time

URL = os.environ["CKURL"]

def rpc(method, params):
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    for attempt in range(5):
        try:
            req = urllib.request.Request(URL, data=body, headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                d = json.load(r)
            if "error" in d:
                sys.stderr.write(f"RPC error {method}: {d['error']}\n")
                time.sleep(0.5); continue
            return d["result"]
        except Exception as e:
            sys.stderr.write(f"attempt {attempt} {method}: {e}\n")
            time.sleep(0.8)
    return None

def get_tx(sig, maxver=0):
    return rpc("getTransaction", [sig, {"encoding":"jsonParsed","maxSupportedTransactionVersion":maxver,"commitment":"confirmed"}])

if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "tx":
        sig = sys.argv[2]
        mv = int(sys.argv[3]) if len(sys.argv)>3 else 0
        out = get_tx(sig, mv)
        print(json.dumps(out))
    elif cmd == "raw":
        method = sys.argv[2]
        params = json.loads(sys.argv[3])
        print(json.dumps(rpc(method, params)))
