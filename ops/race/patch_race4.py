#!/usr/bin/env python3
# RACE-GATE patch part 4 (2026-10-18): the "RACE obs" log line also lists every outside tx seen (ms:sol:buy, first 24) so
# any window/threshold can be re-evaluated offline from one forward run.
import sys
ep = sys.argv[1]
e = open(ep).read()
old = """                let first = p.out.first().map(|o| o.0).unwrap_or(-1.0);"""
new = """                let first = p.out.first().map(|o| o.0).unwrap_or(-1.0);
                let outs: String = p.out.iter().take(24).map(|o| format!("{:.1}:{:.3}:{}:{}", o.0, o.2 as f64 / 1e9, o.4 as u8, &b58(&o.1)[..6])).collect::<Vec<_>>().join(",");"""
assert e.count(old) == 1
e = e.replace(old, new)
old2 = """first_ms={first:.1} bundle_n={} fired={}",
                        p.slot, b58(mint), s100 as f64 / 1e9, s200 as f64 / 1e9, sall as f64 / 1e9, p.bundle_n, p.pass);"""
new2 = """first_ms={first:.1} bundle_n={} fired={} outs={}",
                        p.slot, b58(mint), s100 as f64 / 1e9, s200 as f64 / 1e9, sall as f64 / 1e9, p.bundle_n, p.pass, if outs.is_empty() { "-".to_string() } else { outs });"""
assert e.count(old2) == 1, e.count(old2)
e = e.replace(old2, new2)
open(ep, "w").write(e)
print("patch4 OK")
