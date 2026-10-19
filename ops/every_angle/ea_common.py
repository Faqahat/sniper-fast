import json, requests, time, sys, os

RPC = open('/root/snipe_study50/rpc_url.txt').read().strip()
WALLET = "4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

def rpc(method, params, tries=6):
    for i in range(tries):
        try:
            r = requests.post(RPC, json={"jsonrpc":"2.0","id":1,"method":method,"params":params}, timeout=40)
            j = r.json()
            if 'result' in j: return j['result']
            if 'error' in j:
                err = j['error']
                if err.get('code') == -32019 or 'rate' in str(err).lower():
                    time.sleep(1.0); continue
                return None
        except Exception:
            time.sleep(0.7)
    return None

def load_tape():
    return json.load(open('/root/mirror/his_tape.json'))

# ---- stats helpers ----
def mean(xs):
    xs=[x for x in xs if x is not None]
    return sum(xs)/len(xs) if xs else float('nan')
def median(xs):
    xs=sorted(x for x in xs if x is not None)
    n=len(xs)
    if n==0: return float('nan')
    return xs[n//2] if n%2 else (xs[n//2-1]+xs[n//2])/2
def winrate(xs, thr=0.0):
    xs=[x for x in xs if x is not None]
    return sum(1 for x in xs if x>thr)/len(xs) if xs else float('nan')

def split_oos(tape):
    """chronological split by create_slot: IS=first half, OOS=second half"""
    t=sorted(tape, key=lambda d:d['create_slot'])
    n=len(t); h=n//2
    return t[:h], t[h:]

def pump_metric(d, key='peak_r'):
    return d.get(key)
