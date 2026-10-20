import os
os.chdir("/root/sniper-fast")

# 1) snipe.rs: add is_bot_launchpad (idempotent)
f = "src/snipe.rs"
s = open(f).read()
if "pub fn is_bot_launchpad" in s:
    print("snipe.rs already has is_bot_launchpad")
else:
    anchor = "/// URI-HOST selection gate (reverse-engineered from 4yFAz, OOS lift ~3.7): he snipes tokens launched via the official"
    add = r'''/// URI-HOST BLACKLIST gate ("like the wallet"): fire on EVERYTHING except the pure bundler-bot launch tools 4yFAz
/// never buys from (gg.sc, launchblitz, jake-workers, googleapis, *.trycloudflare). Keeps his whole legit host tail.
pub fn is_bot_launchpad(tx: &Tx) -> bool {
    const BOT: [&str; 4] = ["gg.sc", "ipfs.launchblitz.ai", "pf.jake-98f.workers.dev", "storage.googleapis.com"];
    match launch_uri(tx) {
        Some(u) => { let h = uri_host(&u); BOT.iter().any(|b| *b == h) || h.ends_with(".trycloudflare.com") }
        None => false,
    }
}

'''
    assert s.count(anchor) == 1, ("snipe anchor", s.count(anchor))
    s = s.replace(anchor, add + anchor, 1)
    open(f, "w").write(s)
    print("snipe.rs ok")

# 2) snipe_engine.rs: add --uri-blacklist flag + gate in live and paper (idempotent)
f = "src/bin/snipe_engine.rs"
s = open(f).read()
if "--uri-blacklist" in s:
    print("snipe_engine.rs already has blacklist")
else:
    def rep(old, new, n):
        global s
        assert s.count(old) == n, (old[:60], s.count(old))
        s = s.replace(old, new)
    # add flag right after each uri_whitelist decl (appears twice: live + paper)
    rep('    let uri_whitelist = has("--uri-whitelist");',
        '    let uri_whitelist = has("--uri-whitelist");\n    let uri_blacklist = has("--uri-blacklist");', 2)
    # add blacklist gate right after each whitelist gate (appears twice)
    rep('        if uri_whitelist && !snipe::trusted_launch_host(&a.tx) { skipped_host += 1; continue; }',
        '        if uri_whitelist && !snipe::trusted_launch_host(&a.tx) { skipped_host += 1; continue; }\n        if uri_blacklist && snipe::is_bot_launchpad(&a.tx) { skipped_host += 1; continue; }', 2)
    open(f, "w").write(s)
    print("snipe_engine.rs ok")
