"""arbx-report CLI (MEASUREMENT.md §6.1).

    python3 -m arbx_report <command> <segment-or-campaign-dir> [options]

Commands: segment, campaign, quality, ledger, funnel, attempts, blockctx, attribution, latency, leaders, feeds,
predictions, rivals, experiments [x2|x4|size|margin|x5|x8|x9|all] (a segment or a campaign directory), census, sizes,
sizefit, caps, cu-table, compare A B.
Reports go to <seg>/report/ (or --out). Nothing is fetched from the network unless --rpc-url-env names an
environment variable holding the RPC URL; .env files are never read.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import chain as chainmod
from . import model, quote, render, runner, solana, streams
from .reports import r10_experiments, r13_compare

COMMANDS = ["segment", "campaign", "quality", "ledger", "funnel", "attempts", "blockctx", "attribution", "latency",
            "leaders", "feeds", "predictions", "rivals", "experiments", "census", "sizes", "sizefit", "caps",
            "cu-table", "compare"]


def repo_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def load_tip_accounts(path: str | None) -> set | None:
    p = path or os.path.join(repo_root(), "data", "sender-tip-accounts.json")
    if not os.path.exists(p):
        return None
    with open(p) as f:
        d = json.load(f)
    out = set()
    for v in d.values():
        if isinstance(v, dict):
            out.update(x for x in v.get("tip_accounts") or [] if isinstance(x, str))
    return out or None


def load_wallet_txs(path: str | None) -> list | None:
    if not path:
        return None
    files = []
    if os.path.isdir(path):
        files = [os.path.join(path, f) for f in sorted(os.listdir(path)) if f.endswith((".json", ".jsonl", ".jsonl.xz", ".json.xz"))]
    else:
        files = [path]
    out = []
    for f in files:
        out.extend(solana.load_tx_file(f))
    return out


def load_chain_ledger(path: str | None) -> list | None:
    if not path:
        return None
    with open(path) as f:
        return [json.loads(x) for x in f if x.strip()]


def build_ctx(args) -> dict:
    offline = args.offline or not args.rpc_url_env
    pricer = quote.ArbxQuote(args.arbx_bin)
    return {"offline": offline, "quick": args.quick, "fill_gaps": args.fill_gaps, "pricer": pricer,
            "rpc_url_env": None if offline else args.rpc_url_env}


def open_segment(path: str, args, ctx: dict) -> model.Segment:
    seg = model.Segment(path, wallet_txs=load_wallet_txs(args.wallet_txs), chain_ledger=None)
    cl = load_chain_ledger(args.chain_ledger)
    if cl is not None:
        seg._chain_ledger_extra = [r for r in cl if r.get("seg") in (None, seg.name)]
    if args.wallet:
        seg.__dict__["wallet"] = args.wallet
    seg.tip_accounts = load_tip_accounts(args.tip_accounts)
    ctx["chain"] = chainmod.Chain(os.path.join(seg.dir, "chain-cache"), ctx.get("rpc_url_env"), ctx["offline"])
    return seg


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="arbx-report", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=COMMANDS)
    ap.add_argument("path", help="segment directory (campaign: campaign directory; compare: segment A)")
    ap.add_argument("extra", nargs="?", help="compare: segment B; experiments: x2|x4|size|margin|x5|x8|x9|all")
    ap.add_argument("--out", help="output directory (default <seg>/report)")
    ap.add_argument("--rpc-url-env", help="name of the environment variable holding the RPC URL (never a URL)")
    ap.add_argument("--offline", action="store_true", help="forbid every network call")
    ap.add_argument("--fill-gaps", action="store_true", help="blockctx: fetch full blocks for gap slots")
    ap.add_argument("--quick", action="store_true", help="skip scans of large binary/text streams and hashing of large files")
    ap.add_argument("--match", help="campaign: regex on segment names (e.g. '^w5h2-p')")
    ap.add_argument("--wallet", help="wallet pubkey (default: meta.json)")
    ap.add_argument("--wallet-txs", help="v1 runs: wallet getTransaction results (file, JSON lines, or directory)")
    ap.add_argument("--chain-ledger", help="v1 runs: research chain ledger rows (ledger-w5h2w5h3.jsonl format)")
    ap.add_argument("--tip-accounts", help="tip account map (default data/sender-tip-accounts.json)")
    ap.add_argument("--arbx-bin", help="arbx binary with `quote` (WP-09) for R4/R8/X3")
    ap.add_argument("--stdout", action="store_true", help="print report.json instead of writing files")
    args = ap.parse_args(argv)
    ctx = build_ctx(args)

    if args.command == "experiments" and not model.is_segment_dir(args.path) and os.path.isdir(args.path):
        # WP-11: a campaign directory: every segment's attempts, the ledger across them
        camp = model.Campaign.open(args.path, args.match)
        tips = load_tip_accounts(args.tip_accounts)
        for s in camp.segments:
            s.tip_accounts = tips
        sec = r10_experiments.run(camp, ctx, args.extra or "all")
        doc = {"schema": "arbx.report/1.0", "tool": render.TOOL_VERSION, "kind": "experiments", "name": camp.name, "campaign_json": camp.campaign_json,
               "sections": [sec], "inputs": [{"segment": s.name, **i} for s in camp.segments for i in runner._inputs(s, ctx)]}
        return _emit(doc, args.out or os.path.join(args.path, "report"), "experiments", args.stdout)

    if args.command == "campaign":
        wt = load_wallet_txs(args.wallet_txs)
        cl = load_chain_ledger(args.chain_ledger)
        camp = model.Campaign.open(args.path, args.match, wallet_txs=wt, chain_ledger=cl)
        tips = load_tip_accounts(args.tip_accounts)
        for s in camp.segments:
            s.tip_accounts = tips
            if args.wallet:
                s.__dict__["wallet"] = args.wallet
        ctx["chain"] = chainmod.Chain(None, ctx.get("rpc_url_env"), ctx["offline"])
        doc = runner.campaign(camp, ctx)
        return _emit(doc, args.out or os.path.join(args.path, "report"), "campaign", args.stdout)

    seg = open_segment(args.path, args, ctx)
    out = args.out or os.path.join(seg.dir, "report")
    if args.command == "compare":
        if not args.extra:
            ap.error("compare needs two segments")
        seg_b = open_segment(args.extra, args, dict(ctx))
        names = ["ledger", "funnel", "attempts"]
        sa = {s["id"]: s for s in runner.run_sections(seg, dict(ctx), names)}
        sb = {s["id"]: s for s in runner.run_sections(seg_b, dict(ctx), names)}
        sec = r13_compare.run(seg, seg_b, sa, sb)
        doc = runner.document(seg, ctx, [sec], kind="compare")
        doc["inputs"] = [{"segment": seg.name, **i} for i in doc["inputs"]] + \
                        [{"segment": seg_b.name, **i} for i in runner._inputs(seg_b, ctx)]
        return _emit(doc, out, f"compare-{seg_b.name}", args.stdout)
    if args.command == "segment":
        doc = runner.segment(seg, ctx)
        if not seg.legacy and seg.has("slotidx"):
            runner.write_blockctx(seg, ctx, out) if not args.stdout else None
        return _emit(doc, out, "report", args.stdout)
    if args.command == "blockctx":
        sec = runner.write_blockctx(seg, ctx, out)
        doc = runner.document(seg, ctx, [sec], kind="blockctx")
        return _emit(doc, out, "blockctx-summary", args.stdout)
    if args.command == "experiments":
        which = args.extra or "all"
        doc = runner.document(seg, ctx, [r10_experiments.run(seg, ctx, which)], kind="experiments")
        return _emit(doc, out, "experiments", args.stdout)
    if args.command == "ledger":
        secs = runner.run_sections(seg, ctx, ["ledger"])
        rows = runner.ledger_rows(seg, ctx)
        if rows and not args.stdout:
            render.write_jsonl(os.path.join(out, "ledger.toolkit.jsonl"), rows)
        secs[0]["data"]["toolkit_ledger_rows"] = len(rows)
        secs[0]["data"]["toolkit_identity_violations"] = sum(1 for r in rows if r["identity_violations"])
        doc = runner.document(seg, ctx, secs, kind="ledger")
        return _emit(doc, out, "ledger", args.stdout)
    if args.command == "cu-table":
        doc = runner.document(seg, ctx, runner.run_sections(seg, ctx, ["cu-table"]), kind="cu-table")
        if not args.stdout:
            render.write_atomic(os.path.join(out, "cu-table.json"), render.dumps(doc["sections"][0]["data"].get("table")))
        return _emit(doc, out, "cu-table-report", args.stdout)
    doc = runner.document(seg, ctx, runner.run_sections(seg, ctx, [args.command]), kind=args.command)
    return _emit(doc, out, args.command, args.stdout)


def _emit(doc: dict, out: str, name: str, to_stdout: bool) -> int:
    if to_stdout:
        sys.stdout.write(render.dumps(doc))
        return 0
    pj, pm = render.write_report(out, doc, name)
    print(f"wrote {pj} and {pm}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except streams.SchemaError as e:
        print(f"refused: {e}", file=sys.stderr)
        sys.exit(2)
