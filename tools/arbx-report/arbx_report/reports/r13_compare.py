"""R13 Compare (MEASUREMENT.md §6.4): provenance diff (normalized config, binary and program hashes) and metrics
side by side, so segments are compared only when their provenance differs in known ways."""
from __future__ import annotations

from . import section


def provenance(seg) -> dict:
    m = seg.meta or {}
    if seg.legacy or not m:
        keys = ["strategy", "live", "gate", "sim", "exec", "canary", "send_paths", "feeds", "pools", "wallet"]
        return {"format": "v1", **{k: m.get(k) for k in keys if k in m}}
    b, c = m.get("build") or {}, m.get("config") or {}
    return {"format": "v2", "binary_sha256": b.get("binary_sha256"), "git_commit": b.get("git_commit"),
            "git_dirty": b.get("git_dirty"), "config_normalized_sha256": c.get("normalized_sha256"),
            "programs": {p.get("id"): p.get("elf_sha256") for p in m.get("programs") or []},
            "mode": (m.get("run") or {}).get("mode"), "strategy": m.get("strategy"), "send": m.get("send"),
            "builder": m.get("builder"), "tips": m.get("tips"), "experiments": m.get("experiments"),
            "limits": m.get("limits")}


def _diff(a, b, path="") -> list:
    out = []
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b), key=str):
            out += _diff(a.get(k), b.get(k), f"{path}.{k}" if path else str(k))
    elif a != b:
        out.append({"key": path, "a": a, "b": b})
    return out


def metrics(sec_by_id: dict) -> dict:
    r1 = (sec_by_id.get("R1") or {}).get("data") or {}
    r2 = (sec_by_id.get("R2") or {}).get("data") or {}
    r3 = (sec_by_id.get("R3") or {}).get("data") or {}
    rec = r1.get("recorded") or {}
    tr = r1.get("trading") or {}
    return {"trade_net": tr.get("trade_net", r1.get("trade_net_chain_corrected", rec.get("trade_net_recorded"))),
            "wins": tr.get("wins", rec.get("wins")), "landed_failures": tr.get("landed_failures", rec.get("landed_failures")),
            "attempts": dict(r2.get("stages") or []).get("attempts (signed)"),
            "land_rate": (r3.get("land_rate") or {}).get("rate"),
            "would_fail_rate": ((r3.get("realised_over_expected_landed_only") or {}).get("beside_would_fail") or {}).get("rate")}


def run(seg_a, seg_b, secs_a: dict, secs_b: dict) -> dict:
    sec = section("R13", f"Compare {seg_a.name} vs {seg_b.name}")
    pa, pb = provenance(seg_a), provenance(seg_b)
    sec["data"]["provenance_diff"] = _diff(pa, pb)
    ma, mb = metrics(secs_a), metrics(secs_b)
    sec["data"]["metrics"] = {k: {"a": ma.get(k), "b": mb.get(k)} for k in sorted(set(ma) | set(mb))}
    if pa.get("format") != pb.get("format"):
        sec["caveats"].append("comparing a v1 (arb-lab) segment with a v2 one: see MEASUREMENT §7 for fields that differ")
    return sec
