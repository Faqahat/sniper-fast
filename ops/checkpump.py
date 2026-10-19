import json, subprocess, base64, struct, os
RPC = os.environ['RPC']
rows = """ABDE317qDgPVvcpFeySbKeoazJ9xwumeuFHuff8Dpump Gcf3JB2A9yjxNU2DvfDZtUpVrEBHR1NYUDDU5u7hwgAA 5000000000
HZChLkkT988qnqLjge5Eo4DEpFyVUhdAxPNMuJYRLVvG CYXeFhZY3yBHDMAhFy6oV6Kry99t4y9Z9yn3Wz6BTSFc 12000000000
CDz6rCMeqhAcu8RfQrf9uTtUvVtq9LXF5v2wKmjCSvsB 4wQYtZw8LyBhgFqEF8BZ17stdN3EzQ2pXrfiPQW7ECSP 5000000000
7T3uRkoNzvKKA8hSRPzse1zmtm8zuUavDkEgD5k3pump F1qV2FARU9DXWwm8k1Uo6TT5GJc22uxMupHNUTCcXXp 4000000000
83FPQNafq6pMJ4E8J85h3ciqDcMxW36FQfB2JPgGpump EzLZJXttuBjy66ppkBByWMLuyZ52hP85TJHsRLVRYQCk 2880000000
8CdNTxMrdrYY6LBs6takoR9A3svPbdEiX6muuNmypump zFsBaE5YEGLmqTDu7Xw2d56NoosVPGT1unep7Uuiad9 1000000000
nsVLUoMEPy33eWNvrR5RbhWRocCpyEEcdUze1trpump 8DVVXTCiANwvTSGRZ5KhgPTV4HczpUSKrESyqhmsDH9C 800000000
7RXLJpweKcLFe7vuxYKnCdFfLULTTmBNnNEqThUpump 7NpRbaSe8jGXEieuwfa2d1C1ZJDd3vHvmMwXnBf6FCpN 2900000000
9xDFkqwiasGqCTatJm9uQLton5Mwbo4nyoQFMqfUpump 2r1PBXU1TLpUoL9hiZ9xrt4JT4qXvr2haLGnTPmfvztR 5000000000"""
def floor_px(dev): vq=30e9+dev; return vq*vq/(30e9*1.073e15)
def curve(addr):
    q=json.dumps({"jsonrpc":"2.0","id":1,"method":"getAccountInfo","params":[addr,{"encoding":"base64","commitment":"confirmed"}]})
    r=subprocess.run(["curl","-s","--max-time","10",RPC,"-X","POST","-H","content-type: application/json","-d",q],capture_output=True,text=True)
    v=json.loads(r.stdout)["result"]["value"]
    if v is None: return None  # curve gone (graduated)
    raw=base64.b64decode(v["data"][0])
    vt=struct.unpack("<Q",raw[8:16])[0]; vq=struct.unpack("<Q",raw[16:24])[0]
    complete = raw[48] if len(raw)>48 else 0
    return (vq/vt if vt else 0, complete, vq)
print(f"{'mint':12} {'dev':>5} {'cur/floor':>9} {'real_sol':>9} {'verdict'}")
for line in rows.splitlines():
    m,bc,dev=line.split(); dev=int(dev)
    fl=floor_px(dev); c=curve(bc)
    tag = "FILLED" if m.startswith("HZChLk") else "revert"
    if c is None: print(f"{m[:10]:12} {dev/1e9:5.1f} {'GRADUATED':>9} {'':>9} RAN HARD ({tag})"); continue
    px,comp,vqlam=c
    mult=px/fl if fl else 0
    real_sol=(vqlam-30e9)/1e9
    verdict = "RAN" if mult>1.3 else ("up a bit" if mult>1.05 else "dead/floor")
    print(f"{m[:10]:12} {dev/1e9:5.1f} {mult:8.2f}x {real_sol:8.2f} {verdict} ({tag})")
