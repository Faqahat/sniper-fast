#!/usr/bin/env python3
# RACE-GATE patch part 5 (2026-10-18): de-duplicate txs in the race window by signature. With two feeds (erpc + Kaldera)
# every tx arrives twice, which doubled the outside-SOL count (forward run v1 passed ~50% instead of ~10%).
import sys
ep = sys.argv[1]
e = open(ep).read()
def rep(old, new):
    global e
    assert e.count(old) == 1, old[:80]
    e = e.replace(old, new)
rep("""    decided: bool,
    static_ok: bool,
    pass: bool,
}""", """    decided: bool,
    static_ok: bool,
    pass: bool,
    /// signatures already counted (the same tx arrives once per feed)
    sigs: std::collections::HashSet<[u8; 64]>,
}""")
rep("""            decided: fire_now || !self.cfg.gate || !static_ok, static_ok, pass: fire_now });""",
    """            decided: fire_now || !self.cfg.gate || !static_ok, static_ok, pass: fire_now, sigs: Default::default() });""")
rep("""            let Some(p) = self.pend.get_mut(&mint) else { continue };
            let ms = p.t0.elapsed().as_secs_f64() * 1e3;""", """            let Some(p) = self.pend.get_mut(&mint) else { continue };
            if !p.sigs.insert(tx.sig) { continue; } // duplicate delivery from the second feed
            let ms = p.t0.elapsed().as_secs_f64() * 1e3;""")
open(ep, "w").write(e)
print("patch5 OK")
