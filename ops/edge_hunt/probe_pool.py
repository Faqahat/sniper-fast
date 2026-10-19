import sys,os,json
sys.path.insert(0,"/root/profit_backtest")
import common as C
PUMPSWAP="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
WSOL="So11111111111111111111111111111111111111112"
mint="2t6Z9BiZBkyoxq3gH7nn9mD269MU3YdM6PW1a9NGpump"
sig="661KJPjmmsWBfu58QphJN1LtWEMdCQjGxpcKbJGwEZmLJcUAnKUPFM3DPpVoimzAvvevkxAqMzjWrZcNqgNv6ekW"
tx=C.gettx(sig)
meta=tx["meta"]
print("=== postTokenBalances ===")
for t in meta.get("postTokenBalances",[]):
    amt=float(t["uiTokenAmount"]["uiAmountString"] or 0)
    print(f"  mint={t['mint'][:8]} owner={t.get('owner')} amt={amt:.4f} acctIdx={t.get('accountIndex')}")
# find pool: the account that owns both a big mint balance AND a WSOL balance = pool vaults' authority
# base vault = token acct of mint with largest post amount (owner=pool)
keys=C._keys(tx)
# WSOL account balances via postTokenBalances (WSOL is SPL too)
print("\n=== SOL (lamports) on key accounts, pre->post ===")
for i,k in enumerate(keys):
    pre=meta["preBalances"][i]/1e9; post=meta["postBalances"][i]/1e9
    if abs(post-pre)>0.5 or post>1:
        print(f"  [{i}] {k[:12]} {pre:.3f}->{post:.3f} d={post-pre:+.3f}")
