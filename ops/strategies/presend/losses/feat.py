"""Shared features (decision-time only, labelled) for each position row."""
import json
RUNS = ["r28", "r34", "r35", "r36"]
D = "/home/moiz/sniper-data/presend_losses"
def load(run): return json.load(open(f"{D}/fills_{run}.json"))
def feats(r):
    f, ex, tp = r["fill"], r["exit"], r["tape"]
    oth = [x for x in tp if not x["ours"] and (x["slot"], x["idx"]) > (f["slot"], f["idx"])]
    dec_t = ex["t"] or f["t"] + 200e6
    seen = [x for x in oth if x["t"] < dec_t]
    s1 = r["sells"][0] if r["sells"] else None
    before_sell = [x for x in oth if s1 and (x["slot"], x["idx"]) < (s1["slot"], s1["idx"])]
    sells_seen = [x for x in seen if not x["buy"]]; buys_seen = [x for x in seen if x["buy"]]
    sells_hold = [x for x in before_sell if not x["buy"]]
    d = r["dump"] or {}
    a = r["arm"] or {}
    q = (a.get("quiet") or {})
    o = dict(
        pnl=r["pnl"], size=(r["sol_in"] or 0) / 1e9,
        drop=d.get("drop_pct"), dump_sol=d.get("sell"), dump_vsol=d.get("vsol"), age=d.get("age"),
        late_slots=(f["slot"] - d["slot"]) if d else None, late_ms=((f["t"] - d["t"]) / 1e6) if d else None,
        send_rx=f["ms_send_to_rx"], client=f["client"], path=f["path"], sat=f["slots_after_trigger"], sas=f["slots_after_send"],
        pre_over_lim=(f["p_pre"] / f["lim"]) if f.get("p_pre") and f.get("lim") else None,
        trig_pct=a.get("pct"), trig_sol=a.get("sol"), trig_age=a.get("age_slots"), trig_vsol=a.get("vsol"),
        wh_dumps=q.get("wh_dumps"), wh_fol=q.get("wh_fol"), coh_hold=q.get("coh_hold"), fb_n=q.get("fb_n"), since_last=q.get("since_last"),
        q=q.get("q"), whale=a.get("wallet"),
        seen_sell_sol=sum(x["sol"] for x in sells_seen) / 1e9, seen_buy_sol=sum(x["sol"] for x in buys_seen) / 1e9,
        seen_max_sell=max([x["sol"] for x in sells_seen], default=0) / 1e9,
        hold_sell_sol=sum(x["sol"] for x in sells_hold) / 1e9, hold_buy_sol=sum(x["sol"] for x in before_sell if x["buy"]) / 1e9,
        hold_max_sell=max([x["sol"] for x in sells_hold], default=0) / 1e9,
        whale_sold_in_hold=any(x["user"] == a.get("wallet") for x in sells_hold),
        sell_slot_d=(s1["slot"] - f["slot"]) if s1 else None, dec_ms=(dec_t - f["t"]) / 1e6,
        exit_why=ex["why"], nbuys=r["nbuys"])
    return o
