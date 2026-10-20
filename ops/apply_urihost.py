import os
os.chdir("/root/sniper-fast")

# --- 1) snipe.rs: add 3 helper fns (idempotent) ---
f = "src/snipe.rs"
s = open(f).read()
if "pub fn trusted_launch_host" in s:
    print("snipe.rs already has helpers, skipping")
else:
    anchor = "/// Parsed create/create_v2 args: the creator and (create_v2) the trailing flags. All default when absent (defensive)."
    helpers = r'''/// Extract the metadata URI (3rd borsh string) from a create/create_v2 tx. Zero RPC: it is in the ix data.
pub fn launch_uri(tx: &Tx) -> Option<String> {
    let create = match ix_with_disc(tx, &CREATE_V2_DISC) { Some(ix) => ix, None => ix_with_disc(tx, &CREATE_DISC)? };
    let data = &create.data;
    let mut p = 8usize;
    let mut uri = None;
    for i in 0..3 {
        let len = data.get(p..p + 4).and_then(|b| b.try_into().ok()).map(u32::from_le_bytes)? as usize;
        let start = p + 4;
        let end = start.checked_add(len)?;
        if i == 2 { uri = data.get(start..end).map(|b| String::from_utf8_lossy(b).into_owned()); }
        p = end;
    }
    uri
}

/// Host of a metadata URI, e.g. "ipfs.io" from "https://ipfs.io/ipfs/..". The launch-tool fingerprint.
pub fn uri_host(uri: &str) -> &str {
    uri.split("://").nth(1).unwrap_or(uri).split('/').next().unwrap_or("")
}

/// URI-HOST selection gate (reverse-engineered from 4yFAz, OOS lift ~3.7): he snipes tokens launched via the official
/// pump UI / trusted launchpads and skips third-party bundler-bot launch tools. True = trusted host.
pub fn trusted_launch_host(tx: &Tx) -> bool {
    const HOSTS: [&str; 4] = ["ipfs.io", "metadata.j7tracker.io", "m.rapidlaunch.io", "gateway.pinata.cloud"];
    launch_uri(tx).map(|u| { let h = uri_host(&u); HOSTS.iter().any(|x| *x == h) }).unwrap_or(false)
}

'''
    assert s.count(anchor) == 1, ("snipe anchor", s.count(anchor))
    s = s.replace(anchor, helpers + anchor, 1)
    open(f, "w").write(s)
    print("snipe.rs ok")

# --- 2) snipe_engine.rs edits (idempotent) ---
f = "src/bin/snipe_engine.rs"
s = open(f).read()
if "--uri-whitelist" in s:
    print("snipe_engine.rs already patched, skipping")
else:
    def rep(old, new, n=1):
        global s
        assert s.count(old) == n, (old[:55], s.count(old))
        s = s.replace(old, new, n)

    # live: counters after skipped_far (unique)
    rep("    let mut skipped_far = 0u64;",
        '    let mut skipped_far = 0u64;\n    let uri_whitelist = has("--uri-whitelist");\n    let mut skipped_host = 0u64;')
    # live: gate inserted BEFORE the leader-proximity comment (unique to run_snipe_live)
    rep("        // leader-proximity gate: only fire when the create slot's leader is close (skip far/unknown).",
        "        if uri_whitelist && !snipe::trusted_launch_host(&a.tx) { skipped_host += 1; continue; }\n        // leader-proximity gate: only fire when the create slot's leader is close (skip far/unknown).")
    # live: report after close-leader report (unique)
    rep('    if close_set.is_some() { eprintln!("CLOSE-LEADER GATE: skipped {skipped_far} far/unknown-leader launches"); }',
        '    if close_set.is_some() { eprintln!("CLOSE-LEADER GATE: skipped {skipped_far} far/unknown-leader launches"); }\n    if uri_whitelist { eprintln!("URI-HOST GATE: skipped {skipped_host} non-trusted-host launches"); }')
    # paper: counters after skipped_creator (unique)
    rep("    let mut skipped_creator = 0u64;",
        '    let mut skipped_creator = 0u64;\n    let uri_whitelist = has("--uri-whitelist");\n    let mut skipped_host = 0u64;')
    # paper: gate after vanilla check (skipped_flag is paper-only, unique)
    rep("        if !allow_nonvanilla && !launch.is_snipeable() { skipped_flag += 1; continue; }",
        '        if !allow_nonvanilla && !launch.is_snipeable() { skipped_flag += 1; continue; }\n        if uri_whitelist && !snipe::trusted_launch_host(&a.tx) { skipped_host += 1; continue; }')
    # paper: report after creator report (unique)
    rep('    if max_creator_sigs > 0 { eprintln!("CREATOR-FRESHNESS gate (<= {max_creator_sigs} prior sigs): skipped {skipped_creator} non-fresh-deployer launches"); }',
        '    if max_creator_sigs > 0 { eprintln!("CREATOR-FRESHNESS gate (<= {max_creator_sigs} prior sigs): skipped {skipped_creator} non-fresh-deployer launches"); }\n    if uri_whitelist { eprintln!("URI-HOST GATE: skipped {skipped_host} non-trusted-host launches"); }')
    open(f, "w").write(s)
    print("snipe_engine.rs ok")
