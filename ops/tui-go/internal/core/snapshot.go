package core

import (
	"path/filepath"
	"strconv"
	"strings"
)

// athJSON sets ath_sol / ath_t / low_sol / low_t / from_ath_sol (SOL; times in ns: each minute's start) of a series.
func athJSON(d *JObj, s *PnLSeries) {
	if !s.Ok() {
		for _, k := range []string{"ath_sol", "ath_t", "low_sol", "low_t", "from_ath_sol"} {
			d.Set(k, nil)
		}
		return
	}
	d.Set("ath_sol", PyFloat(float64(s.Vals[s.Hi])/LAM))
	d.Set("ath_t", (s.M0+int64(s.Hi))*minuteNS)
	d.Set("low_sol", PyFloat(float64(s.Vals[s.Lo])/LAM))
	d.Set("low_t", (s.M0+int64(s.Lo))*minuteNS)
	d.Set("from_ath_sol", PyFloat(float64(s.FromATH())/LAM))
}

// ATHJSON is athJSON for the UI's extra card objects.
func ATHJSON(d *JObj, s *PnLSeries) { athJSON(d, s) }

// ATHText is the text snapshot's v3 line: "ATH +0.606 SOL  $113.52 · 5:29 PM PKT   low ...   from ATH -0.018".
func ATHText(s *PnLSeries, price float64) string {
	if !s.Ok() {
		return ""
	}
	one := func(x int64, tns float64) string {
		o := SolAuto(x) + " SOL"
		if price != 0 {
			o += "  " + Usd(x, true, price, x < 0, 2)
		}
		return o + " " + G.Sep + " " + T12(tns, false)
	}
	a, at := s.ATH()
	l, lt := s.Low()
	return "ATH       " + one(a, at) + " PKT   low " + one(l, lt) + "   from ATH " + SolAuto(s.FromATH())
}

// SessionTotals is session_totals(S): one session's figures (lamports), the run reports' definitions.
func SessionTotals(S *Sess) *JObj {
	var fills, fail int64
	var wins, guard, light, other, fillPnl, failPnl, est int64
	for _, t := range S.Reg {
		switch t.Res {
		case "filled":
			fills++
			if t.HasPnl {
				fillPnl += t.Pnl
				if t.Pnl > 0 {
					wins++
				}
			}
			if t.Src != "tx" {
				est++
			}
		case "guard", "lighthouse", "failed":
			fail++
			if t.HasPnl {
				failPnl += t.Pnl
			}
		}
		switch t.Res {
		case "guard":
			guard++
		case "lighthouse":
			light++
		case "failed":
			other++
		}
	}
	o := &JObj{}
	o.Set("ps_fills", S.PSFills)
	o.Set("ps_wins", S.PSWins)
	o.Set("ps_real", S.PSRealized)
	o.Set("ps_rent", S.PSRent)
	o.Set("ps_fees", S.PSFees())
	o.Set("ps_fees_counted", S.PSFeeCnt)
	o.Set("ps_net", S.PSNet())
	o.Set("ps_sent", S.PSSent)
	o.Set("reg_fires", int64(len(S.Reg)))
	o.Set("reg_fills", fills)
	o.Set("reg_wins", wins)
	o.Set("reg_guard", guard)
	o.Set("reg_lighthouse", light)
	o.Set("reg_other", other)
	o.Set("reg_fill_pnl", fillPnl)
	o.Set("reg_fail_pnl", failPnl)
	o.Set("reg_total", S.RegTotal())
	o.Set("total", S.Total())
	o.Set("est", est)
	_ = fail
	return o
}

func optInt(v int64, ok bool) any {
	if !ok {
		return nil
	}
	return v
}

func optStr(s string) any {
	if s == "" {
		return nil
	}
	return s
}

func exitsJSON(e *OExits) *JObj {
	o := &JObj{}
	for _, k := range e.Keys {
		x := e.M[k]
		o.Set(k, (&JObj{}).Set("n", x.N).Set("wins", x.Wins).Set("pnl", x.Pnl))
	}
	return o
}

// SnapshotJSON is snapshot_json(v, ctx); extra adds the v3 figures (the trading card, today).
func SnapshotJSON(v *View, ctx *Ctx, extra *JObj) string {
	ps, rg := v.PS, v.Reg
	d := &JObj{}
	d.Set("region", v.Region)
	if v.HasRun {
		d.Set("run", int64(v.Run))
	} else {
		d.Set("run", nil)
	}
	d.Set("file", ctx.Src.JSONL)
	d.Set("status", v.Status)
	d.Set("how_ended", optStr(v.HowEnded))
	d.Set("build", v.Build)
	d.Set("sessions", int64(v.NSess))
	d.Set("started", optInt(v.TFirst, v.TFirst != 0))
	if v.Status == "ENDED" {
		d.Set("ended", optInt(v.TEnd, v.TEnd != 0))
	} else {
		d.Set("ended", nil)
	}
	if v.HasElapsed {
		d.Set("elapsed_s", v.Elapsed)
	} else {
		d.Set("elapsed_s", nil)
	}
	if v.Planned.Ok() {
		d.Set("planned_min", v.Planned)
	} else {
		d.Set("planned_min", nil)
	}
	if v.Price != 0 {
		d.Set("sol_usd", PyFloat(v.Price))
	} else {
		d.Set("sol_usd", nil)
	}
	d.Set("total_lamports", v.Total)
	d.Set("total_sol", PyFloat(float64(v.Total)/LAM))
	if v.HasPerHour {
		d.Set("per_hour_sol", PyFloat(v.PerHour/LAM))
	} else {
		d.Set("per_hour_sol", nil)
	}
	pso := &JObj{}
	pso.Set("active", ps.Active)
	pso.Set("fills", ps.Fills)
	pso.Set("wins", ps.Wins)
	pso.Set("realized", ps.Real)
	pso.Set("rent", ps.Rent)
	pso.Set("fees", ps.Fees)
	pso.Set("fees_counted", ps.FeesCnt)
	pso.Set("fees_engine", ps.FeesEng)
	pso.Set("failed_tries", ps.FeeN)
	pso.Set("net", ps.Net)
	pso.Set("sent", ps.Sent)
	pso.Set("results", ps.Res.JSON())
	pso.Set("armed", ps.Armed)
	pso.Set("skips", ps.Skips.JSON())
	pso.Set("disarms", ps.Disarms.JSON())
	pso.Set("exits", exitsJSON(ps.Exits))
	pso.Set("quiet_skips", ps.QSkips)
	pso.Set("quiet_stops", ps.QStops)
	pso.Set("quiet_would", ps.QWould)
	pso.Set("paper_fills", ps.PaperFills)
	pso.Set("paper_net", PyFloat(ps.PaperNet))
	pso.Set("stopped", optStr(v.PSStopped))
	pso.Set("open_windows", v.PSOpenNow)
	d.Set("presend", pso)
	ro := &JObj{}
	ro.Set("fires", rg.Fires)
	ro.Set("fills", rg.Fills)
	ro.Set("wins", rg.Wins)
	ro.Set("guard_6042", rg.Guard)
	ro.Set("lighthouse_6001", rg.Lighthouse)
	ro.Set("failed_other", rg.Failed)
	ro.Set("open", rg.Open)
	ro.Set("fill_pnl", rg.FillPnl)
	ro.Set("failed_pnl", rg.FailPnl)
	ro.Set("total", rg.Total)
	ro.Set("estimated", rg.Est)
	ro.Set("exits", exitsJSON(rg.Exits))
	bc := &JObj{}
	for _, k := range rg.KindKeys {
		x := rg.Kinds[k]
		bc.Set(k, (&JObj{}).Set("buys", x.Buys).Set("fills", x.Fills).Set("wins", x.Wins).Set("pnl", x.Pnl))
	}
	ro.Set("by_client", bc)
	d.Set("regular", ro)
	wo := &JObj{}
	wo.Set("start", optInt(v.StartBal, v.HasStartBal))
	wo.Set("est_now", optInt(v.EstNow, v.HasEstNow))
	wo.Set("kill_level", optInt(v.KillLevel, v.HasKillLevel))
	wo.Set("kill_distance", optInt(v.KillDist, v.HasKillDist))
	wo.Set("budget_left", optInt(v.BudgetLeft, v.HasBudget))
	d.Set("wallet", wo)
	q := v.Quiet
	qo := &JObj{}
	qo.Set("present", q.Present)
	if q.HasStop {
		qo.Set("stop", q.Stop)
	} else {
		qo.Set("stop", nil)
	}
	if q.HasSkip {
		qo.Set("skip", q.Skip)
	} else {
		qo.Set("skip", nil)
	}
	qo.Set("state", optStr(q.State))
	qo.Set("on_at", optInt(q.OnAt, q.HasOnAt))
	qo.Set("preload", optStr(q.Preload))
	if q.PreloadH.Ok() {
		qo.Set("preload_h", q.PreloadH)
	} else {
		qo.Set("preload_h", nil)
	}
	d.Set("quiet", qo)
	co := &JObj{}
	for _, it := range v.CfgItems {
		co.Set(it.Key, (&JObj{}).Set("state", it.State).Set("short", it.Short))
	}
	d.Set("config", co)
	al := make([]any, 0, len(v.Alerts))
	for _, a := range v.Alerts {
		al = append(al, (&JObj{}).Set("level", a.Level).Set("text", a.Text))
	}
	d.Set("alerts", al)
	pss := make([]any, 0, len(v.Sessions))
	for _, X := range v.Sessions {
		o := &JObj{}
		o.Set("n", int64(X.Idx+1))
		o.Set("start", optInt(X.T0, X.T0 != 0))
		o.Set("end", optInt(X.TEnd(), X.TEnd() != 0))
		o.Set("start_balance", optInt(X.StartBal, X.HasStartBal))
		st := SessionTotals(X)
		for i, k := range st.Keys {
			o.Set(k, st.Vals[i])
		}
		pss = append(pss, o)
	}
	d.Set("per_session", pss)
	if v.HasBest {
		d.Set("series_hi", []any{v.BestVal(), PyFloat(v.Best[1])})
		d.Set("series_lo", []any{v.WorstVal(), PyFloat(v.Worst[1])})
	} else {
		d.Set("series_hi", nil)
		d.Set("series_lo", nil)
	}
	// v3: the ATH / low of the same series (the chart's markers, the card's lines) and the drawdown from the ATH
	athJSON(d, v.PnL())
	if extra != nil {
		for i, k := range extra.Keys {
			d.Set(k, extra.Vals[i])
		}
	}
	return JSONDumps(d)
}

// WrapText hard-wraps a plain string into lines of width w (continuation lines indented).
func WrapText(text string, w, indent int) []string {
	var out []string
	first := true
	s := []rune(text)
	for len(s) > 0 {
		room := w
		if !first {
			room = w - indent
		}
		if room <= 0 {
			break
		}
		pre := ""
		if !first {
			pre = strings.Repeat(" ", indent)
		}
		if len(s) <= room {
			out = append(out, pre+string(s))
			break
		}
		cut := -1
		for i := min(room, len(s)-1); i >= 0; i-- {
			if s[i] == ' ' {
				cut = i
				break
			}
		}
		if cut <= room/3 {
			cut = room
		}
		out = append(out, pre+strings.TrimRight(string(s[:cut]), " \t\n\r\v\f"))
		s = []rune(strings.TrimLeft(string(s[cut:]), " \t\n\r\v\f"))
		first = false
	}
	if len(out) == 0 {
		return []string{""}
	}
	return out
}

// SnapshotText is snapshot_text(v, ctx): the plain-text summary.
func SnapshotText(v *View, ctx *Ctx, width int) string {
	var out []string
	S := v.Cur
	u := v.Price
	region := filepath.Base(ctx.Src.JSONL)
	if v.HasRun {
		region = v.Region + " run " + strconv.Itoa(v.Run)
	}
	end := ""
	if v.Status == "ENDED" && v.TEnd != 0 {
		end = " " + Clock(float64(v.TEnd), "%H:%M") + " PKT (" + pyNone(v.HowEnded) + ")"
	} else if v.HowEnded != "" {
		end = " (" + v.HowEnded + ")"
	}
	out = append(out, "dipmon snapshot  "+region+"  ("+v.Build+")  "+v.Status+end)
	out = append(out, "files     "+ctx.Src.JSONL+" (+ .log)  "+F(float64(ctx.Src.TJ.Size)/1e6, 1)+" MB + "+F(float64(ctx.Src.TL.Size)/1e6, 1)+" MB")
	plan := ""
	if v.Planned.Truthy() {
		plan = " of " + HMS(v.Planned.Float()*60, true, false) + " planned"
	}
	line := "started   " + Clock(float64(v.TFirst), "%Y-%m-%d %H:%M:%S") + " PKT   ran " + HMS(v.Elapsed, v.HasElapsed, false) + plan + "   sessions " + strconv.Itoa(v.NSess)
	if v.Running && v.HasEndsAt {
		line += "   ends " + Clock(v.EndsAt, "%H:%M") + " PKT"
	}
	out = append(out, line)
	if u != 0 {
		s := "SOL/USD   $" + FC(u, 2) + " (" + pyNone(v.PriceSrc)
		if v.PriceAgeOK {
			s += ", " + AgeS(v.PriceAge, true) + " old)"
		} else {
			s += ")"
		}
		out = append(out, s)
	} else {
		out = append(out, "SOL/USD   n/a")
	}
	out = append(out, "")
	ps, rg := v.PS, v.Reg
	m := func(lam int64) string {
		us := "USD n/a"
		if u != 0 {
			us = Usd(lam, true, u, true, 2)
		}
		return SolS(lam) + " SOL  " + us
	}
	ph := G.Dash
	if v.HasPerHour {
		ph = m(int64(v.PerHour))
	}
	out = append(out, "RUN P&L   "+PadRight(m(v.Total), 32)+"  per hour "+ph)
	if ps.Active {
		out = append(out, "pre-send  "+PadRight(m(ps.Net), 32)+"  "+Itoa(ps.Fills)+" fills, "+Itoa(ps.Wins)+" wins | realized "+SolS(ps.Real)+
			", rent back "+SolS(ps.Rent)+", failed tries "+SolS(-ps.Fees)+" ("+IC(ps.FeeN)+" x "+IC(v.PSFailEach)+")")
		if ps.AllStopped && ps.FeesEng != 0 {
			dd := ps.FeesEng - ps.FeesCnt
			tail := "(match)"
			if !(abs64(dd) < v.PSFailEach) {
				tail = "(differ by " + FS(float64(dd)/LAM, 6) + ")"
			}
			out = append(out, "          failed-try fees: counted "+F(float64(ps.FeesCnt)/LAM, 6)+", engine at the end "+F(float64(ps.FeesEng)/LAM, 6)+" "+tail)
		} else if ps.FeesEng != 0 {
			out = append(out, "          failed-try fees: counted "+F(float64(ps.FeesCnt)/LAM, 6)+", engine "+F(float64(ps.FeesEng)/LAM, 6)+" at its last 60 s status line")
		}
	} else {
		out = append(out, "pre-send  off")
	}
	nf := rg.Guard + rg.Lighthouse + rg.Failed
	line = "regular   " + PadRight(m(rg.Total), 32) + "  " + Itoa(rg.Fires) + " buys, " + Itoa(rg.Fills) + " fills, " + Itoa(rg.Wins) + " wins | fills " + SolS(rg.FillPnl) +
		", failed buys " + SolS(rg.FailPnl) + " (" + Itoa(nf) + ": 6042 " + Itoa(rg.Guard) + ", 6001 " + Itoa(rg.Lighthouse) + ", other " + Itoa(rg.Failed) + ")"
	if rg.Open != 0 {
		line += ", " + Itoa(rg.Open) + " open"
	}
	if rg.Est != 0 {
		line += ", " + Itoa(rg.Est) + " on the feed estimate"
	}
	out = append(out, line)
	if v.HasEstNow {
		line = "wallet    start " + F(float64(v.StartBal)/LAM, 4) + "  now " + F(float64(v.EstNow)/LAM, 4) + " est."
		if v.HasKillLevel {
			line += "  kill switch below " + F(float64(v.KillLevel)/LAM, 4) + " (" + F(float64(v.KillDist)/LAM, 3) + " SOL away)"
		}
		if v.HasBudget {
			line += "  budget left " + F(float64(v.BudgetLeft)/LAM, 3)
		}
		out = append(out, line)
	}
	if v.HasBest {
		out = append(out, "P&L line  hi "+Sol(v.BestVal(), true, 3, true)+" "+Clock(v.Best[1], "%H:%M")+"  lo "+Sol(v.WorstVal(), true, 3, true)+" "+Clock(v.Worst[1], "%H:%M")+"  now "+Sol(v.Total, true, 3, true))
		if x := ATHText(v.PnL(), u); x != "" { // v3
			out = append(out, x)
		}
	}
	if ps.Active {
		capS := "?"
		if c := v.PSCfg["max_fills"]; truthyAny(c) {
			capS = fmtAny(c)
		}
		bud := 0.0
		if b, ok := v.PSCfg["fee_budget"].(Num); ok && b.Truthy() {
			bud = b.Float()
		}
		line = "caps      pre-send fills " + Itoa(S.PSFills) + "/" + capS + ", fee budget " + F(float64(S.PSFees())/LAM, 4) + "/" + F(bud/LAM, 4) + " SOL"
		if v.PSStopped != "" {
			line += ", stopped (" + v.PSStopped + ")"
		}
		line += ", windows armed now " + Itoa(v.PSOpenNow)
		out = append(out, line)
		if ps.Paper {
			out = append(out, "paper     row c "+Itoa(ps.PaperFills)+" fills, gross "+FS(ps.PaperGross, 3)+", net "+FS(ps.PaperNet, 3)+" SOL  vs live "+Itoa(ps.Fills)+" fills, net "+Sol(ps.Net, true, 3, true))
		}
	}
	q := v.Quiet
	if q.Present {
		kf := "?"
		if it := v.ItemByKey("qskip"); it != nil {
			kf = it.Full
		}
		stop := "None"
		if q.HasStop {
			stop = q.Stop
		}
		out = append(out, "QUIET     stop "+stop+", skip rule: "+kf+"; skips "+Itoa(ps.QSkips)+", stops "+Itoa(ps.QStops)+", would-skip "+Itoa(ps.QWould))
	}
	parts := make([]string, 0, len(v.CfgItems))
	for _, it := range v.CfgItems {
		p := ""
		if it.State != "na" {
			p = BadgeASCII[it.State] + " "
		}
		parts = append(parts, p+it.Short)
	}
	for i, ln := range WrapText(strings.Join(parts, "  "), width-10, 0) {
		if i == 0 {
			out = append(out, "config    "+ln)
		} else {
			out = append(out, "          "+ln)
		}
	}
	out = append(out, "          (+ on, ~ partial / warming up, - off)")
	if v.NSess > 1 {
		out = append(out, "")
		out = append(out, "sessions  #  start    P&L SOL   pre-send    regular  end")
		for _, X := range v.Sessions {
			e := "?"
			if X.TEnd() != 0 {
				e = Clock(float64(X.TEnd()), "%H:%M")
			} else if X == v.Cur && v.Running {
				e = "now"
			}
			out = append(out, "          "+PadRight(strconv.Itoa(X.Idx+1), 2)+" "+PadRight(Clock(float64(X.T0), "%H:%M"), 6)+" "+PadLeft(SolS(X.Total()), 9)+"  "+
				PadLeft(SolS(X.PSNet()), 9)+"  "+PadLeft(SolS(X.RegTotal()), 9)+"  "+e)
		}
	}
	out = append(out, "")
	out = append(out, "last trades (PKT, newest first; P&L = realized, ~ = feed estimate):")
	tl := SortedTrades(v.Trades, "all")
	for i, tr := range tl {
		if i >= 8 {
			break
		}
		sp := tr.Spend.Int()
		kind := "REG"
		if tr.Kind == "PS" {
			kind = "PS "
		}
		pS := "-"
		uS := ""
		pctS := ""
		if tr.HasPnl {
			est := " "
			if tr.Src == "est" {
				est = "~"
			}
			pS = SolS(tr.Pnl) + est
			if u != 0 {
				uS = Usd(tr.Pnl, true, u, true, 2)
			}
			if sp != 0 {
				pctS = PctS(float64(tr.Pnl)/float64(sp), true, 1, true)
			}
		}
		out = append(out, "  "+Clock(float64(tr.T), "%H:%M:%S")+" "+kind+" "+Short(tr.Mint, 8)+"  "+F(float64(sp)/LAM, 2)+"  "+
			PadLeft(pS, 9)+" "+PadLeft(uS, 9)+"  "+PadLeft(pctS, 7)+"  "+PadRight(TradeExit(tr), 5)+" "+KindOf(tr.Client))
	}
	out = append(out, "")
	if len(v.Alerts) > 0 {
		for _, a := range v.Alerts {
			lvl := "note"
			if a.Level == "bad" {
				lvl = "ALERT"
			} else if a.Level == "warn" {
				lvl = "warn"
			}
			out = append(out, PadRight(lvl, 9)+" "+a.Text)
		}
	} else {
		out = append(out, "alerts    none")
	}
	return strings.Join(out, "\n")
}

func pyNone(s string) string {
	if s == "" {
		return "None"
	}
	return s
}

func abs64(x int64) int64 {
	if x < 0 {
		return -x
	}
	return x
}
