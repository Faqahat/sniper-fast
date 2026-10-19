import os
os.chdir("/root/arbx-fast")

# 1) snipe_engine.rs: inject the path's tip transfer into send_and_poll (tipped paths only; tipless unchanged)
f = "src/bin/snipe_engine.rs"
s = open(f).read()
if "path.tip(0)" in s:
    print("send_and_poll already injects tip")
else:
    anchor = """    let (blockhash, _) = rpc.latest_blockhash().await.context(\"getLatestBlockhash\")?;
    let msg = build::compile_v0(user, ixs, blockhash, &[], &[]).map_err(|e| anyhow::anyhow!(e))?;"""
    assert s.count(anchor) == 1, ("anchor", s.count(anchor))
    repl = """    // Tipped send paths (nozomi / jito-tx / helius / 0slot ...) require a top-level System tip transfer to one of the
    // path's tip accounts, or Path::check refuses the send. Tipless paths (staked-rpc / tpu-direct) return None -> unchanged.
    let _tip_owned: Vec<build::Ix>;
    let ixs: &[build::Ix] = match path.tip(0) {
        Some((tip_to, tip_lam)) if tip_lam > 0 => {
            let mut v = Vec::with_capacity(ixs.len() + 1);
            v.push(build::transfer_ix(user, tip_to, tip_lam));
            v.extend_from_slice(ixs);
            _tip_owned = v;
            &_tip_owned
        }
        _ => ixs,
    };
    let (blockhash, _) = rpc.latest_blockhash().await.context(\"getLatestBlockhash\")?;
    let msg = build::compile_v0(user, ixs, blockhash, &[], &[]).map_err(|e| anyhow::anyhow!(e))?;"""
    s = s.replace(anchor, repl, 1)
    open(f, "w").write(s)
    print("send_and_poll tip injection added")

# 2) probe_shadow.toml: add the Nozomi send path (JSON-RPC Frankfurt endpoint, key from env, 0.002 SOL tip)
f = "probe_shadow.toml"
t = open(f).read()
if 'kind    = "nozomi"' in t or 'kind = "nozomi"' in t:
    print("nozomi send path already in config")
else:
    anchor = '''[[send]]
name    = "staked-rpc"
enabled = true
kind    = "rpc"
url     = "https://staked-rpc-frankfurt.constant-k.com/?api-key=${CONSTANTK_TOKEN}"'''
    assert t.count(anchor) == 1, ("toml anchor", t.count(anchor))
    add = anchor + '''

[[send]]
name    = "nozomi"
enabled = true
kind    = "nozomi"
url     = "http://fra2.nozomi.temporal.xyz/?c=${NOZOMI_KEY}"
tip_lamports = 2000000'''
    t = t.replace(anchor, add, 1)
    open(f, "w").write(t)
    print("nozomi send path added to config")
