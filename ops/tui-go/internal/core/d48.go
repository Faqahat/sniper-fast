package core

import (
	"fmt"
	"sort"
	"strings"
)

// dip48 / dip49 (v5, 11-12): the fresh-holders arm-time skip (T2:RA lanes, the re-arm f1 / f3 definition), the follower-flow log
// (presend_live_flow: outside buys / sells after our fill by class) and the T2 rival gate (per try: presend_live_rival_gate per
// window, rival_gate on fills). Sections join the v5 rule sections; each is absent when its records are.

var flowClasses = []string{"bots", "fleet", "retail", "rivals", "dumper"}

type v5FreshFill struct {
	Pct, Thr float64
	N        int64
	Would    bool
	Def      string
}

type v5Flow struct {
	Buy1, Sell1, Buy2, Sell2 map[string]float64 // class -> SOL through fill+1 / fill+2 (outside: "us" left out)
	B1, S1, B2, S2           float64
	Closed                   string
}

type v5RivalFill struct {
	Rivals        int64
	HasRivals     bool
	DevAge        float64
	HasAge, Young bool
	Src, On, Open string
	Blocked       bool
}

type v5FreshSkip struct {
	T          int64
	Mint, Lane string
	Pct, Thr   float64
	N          int64
	Def        string
}

type v5RivalWin struct {
	T                                    int64
	W                                    int64
	Mint, Mode, Src, Kind                string
	Tries, Passed, Withheld, Would, Open int64
	RivMin                               int64
	DevAge                               float64
	HasAge                               bool
}

// d48 holds the dip48 / dip49 records (V5Acc's part).
type d48 struct {
	freshSkips []v5FreshSkip
	flows      map[FKey]*v5Flow
	nFlow      int64
	rivWins    []v5RivalWin
}

func freshOf(o map[string]any) *v5FreshFill {
	f := mObj(o, "fresh_skip")
	if f == nil {
		return nil
	}
	x := &v5FreshFill{Would: mBool(f, "would_skip")}
	x.Pct, _ = mNum(f, "pct")
	x.Thr, _ = mNum(f, "thr")
	if v, ok := mNum(f, "n"); ok {
		x.N = int64(v)
	}
	if d := mObj(f, "def"); d != nil {
		x.Def = mStr(d, "def")
	}
	return x
}

func rivalOf(o map[string]any) *v5RivalFill {
	r := mObj(o, "rival_gate")
	if r == nil {
		return nil
	}
	x := &v5RivalFill{Young: mBool(r, "young"), Src: mStr(r, "dev_age_src"), On: mStr(r, "on"), Open: mStr(r, "open"), Blocked: mBool(r, "blocked")}
	if v, ok := mNum(r, "rivals"); ok {
		x.Rivals, x.HasRivals = int64(v), true
	}
	if v, ok := mNum(r, "dev_age_h"); ok {
		x.DevAge, x.HasAge = v, true
	}
	return x
}

func (A *V5Acc) d48Feed(e string, o map[string]any) {
	D := &A.d48
	switch e {
	case "presend_live_skip":
		if mStr(o, "why") != "fresh_holders" {
			return
		}
		s := v5FreshSkip{T: tOfAny(o), Lane: "T2", Def: mStr(mObj(o, "fresh_def"), "def")}
		if mStr(o, "kind") == "rearm" {
			s.Lane = "RA"
			s.Mint = mStr(o, "mint")
			if s.T == 0 {
				s.T = tOfAny(mObj(o, "dump"))
			}
		} else if tr := mObj(o, "trig"); tr != nil {
			s.Mint = mStr(tr, "mint")
			if s.T == 0 {
				s.T = tOfAny(tr)
			}
		}
		if s.T == 0 {
			s.T = A.tr.curT
		}
		s.Pct, _ = mNum(o, "fresh")
		s.Thr, _ = mNum(o, "thr")
		if v, ok := mNum(o, "fresh_n"); ok {
			s.N = int64(v)
		}
		D.freshSkips = append(D.freshSkips, s)
	case "presend_live_flow":
		f := &v5Flow{Buy1: map[string]float64{}, Sell1: map[string]float64{}, Buy2: map[string]float64{}, Sell2: map[string]float64{}, Closed: mStr(o, "closed")}
		ps, _ := o["per_slot"].([]any)
		for _, p := range ps {
			x, _ := p.(map[string]any)
			ds, _ := mNum(x, "dslot")
			for _, c := range flowClasses {
				b, _ := mNum(mObj(x, "buy_sol"), c)
				s, _ := mNum(mObj(x, "sell_sol"), c)
				if ds <= 1 {
					f.Buy1[c] += b
					f.Sell1[c] += s
					f.B1 += b
					f.S1 += s
				}
				if ds <= 2 {
					f.Buy2[c] += b
					f.Sell2[c] += s
					f.B2 += b
					f.S2 += s
				}
			}
		}
		if t1 := mObj(o, "tot1"); t1 != nil { // the engine's own totals (outside = all but us)
			f.B1, _ = mNum(t1, "buy")
			f.S1, _ = mNum(t1, "sell")
		}
		if t2 := mObj(o, "tot2"); t2 != nil {
			f.B2, _ = mNum(t2, "buy")
			f.S2, _ = mNum(t2, "sell")
		}
		if D.flows == nil {
			D.flows = map[FKey]*v5Flow{}
		}
		D.flows[FKey{mW(o), mStr(o, "mint")}] = f
		D.nFlow++
	case "presend_live_rival_gate":
		r := v5RivalWin{T: tOfAny(o), W: mW(o), Mint: mStr(o, "mint"), Mode: mStr(o, "mode"), Src: mStr(o, "dev_age_src"), Kind: mStr(o, "kind")}
		get := func(k string) int64 { x, _ := mNum(o, k); return int64(x) }
		r.Tries, r.Passed, r.Withheld, r.Would, r.Open, r.RivMin = get("tries"), get("passed"), get("withheld"), get("would"), get("open"), get("rivals_min")
		if v, ok := mNum(o, "dev_age_h"); ok {
			r.DevAge, r.HasAge = v, true
		}
		D.rivWins = append(D.rivWins, r)
	}
}

// FlowCell / RivalCell: the trade row's cells ("" = none).
func (f *V5Fill) FlowCell() string {
	if f == nil || f.Flow == nil {
		return ""
	}
	return F(f.Flow.B1, 2)
}

func (f *V5Fill) RivalCell() string {
	if f == nil || f.Rival == nil {
		return ""
	}
	r := f.Rival
	s := G.Dash
	if r.HasRivals {
		s = fmt.Sprint(r.Rivals)
	}
	if r.HasAge {
		s += "/" + devAgeS(r.DevAge)
	} else {
		s += "/?"
	}
	return s
}

func devAgeS(h float64) string {
	switch {
	case h >= 1000:
		return "old"
	case h >= 48:
		return fmt.Sprintf("%.0fd", h/24)
	case h >= 10:
		return fmt.Sprintf("%.0fh", h)
	}
	return fmt.Sprintf("%.1fh", h)
}

// d48Brief: the details' dip48 / dip49 part.
func (f *V5Fill) d48Brief() []string {
	var ps []string
	if x := f.Fresh; x != nil {
		s := fmt.Sprintf("fresh %.1f%% (%d holders, thr %.0f%%", x.Pct, x.N, x.Thr)
		if x.Def != "" {
			s += ", " + x.Def
		}
		s += ")"
		if x.Would {
			s += " would skip"
		}
		ps = append(ps, s)
	}
	if r := f.Rival; r != nil {
		s := "rivals " + f.RivalCell() + " (dev age src " + orDash(r.Src) + ", " + orDash(r.On) + ")"
		if r.Blocked {
			s += " would block"
		}
		if r.Open != "" {
			s += " open " + r.Open
		}
		ps = append(ps, s)
	}
	if fl := f.Flow; fl != nil {
		var cs []string
		for _, c := range flowClasses {
			if fl.Buy1[c] != 0 || fl.Sell1[c] != 0 {
				cs = append(cs, fmt.Sprintf("%s %.2f/%.2f", c, fl.Buy1[c], fl.Sell1[c]))
			}
		}
		ps = append(ps, fmt.Sprintf("flow +1 buy %.2f sell %.2f (%s) · +2 buy %.2f sell %.2f", fl.B1, fl.S1, strings.Join(cs, ", "), fl.B2, fl.S2))
	}
	return ps
}

// ---- sections

func (A *V5Acc) secFresh(R *V5Report) *D43Section {
	D := &A.d48
	mode, spec, def := rawStr(A.fsCur["fresh_skip"]), rawStr(A.fsCur["fresh_skip_spec"]), rawStr(A.fsCur["fresh_skip_ra_def"])
	if _, ok := A.fsCur["fresh_skip_ra_def"]; !ok && mode != "" && mode != "off" {
		def = "f3 (dip48)"
	}
	var fills []*V5Fill
	for _, f := range R.Fills {
		if f.Fresh != nil {
			fills = append(fills, f)
		}
	}
	if len(D.freshSkips) == 0 && len(fills) == 0 && (mode == "" || mode == "off") {
		return nil
	}
	s := &D43Section{Key: "fresh_skip", Title: "FRESH-HOLDERS SKIP (dip48 / dip49: fresh holders' share at the arm)", JSON: &JObj{}}
	s.Lines = append(s.Lines, fmt.Sprintf("mode %s · spec %s (T2 %% : re-arm %%, 0 = lane off) · re-arm definition %s", strings.ToUpper(orDash(mode)), orDash(spec), orDash(def)))
	byLane := map[string]int{}
	for _, k := range D.freshSkips {
		byLane[k.Lane]++
	}
	s.Lines = append(s.Lines, fmt.Sprintf("skipped live: T2 %d · re-arm %d", byLane["T2"], byLane["RA"]))
	for i := len(D.freshSkips) - 1; i >= 0 && len(D.freshSkips)-1-i < 15; i-- {
		k := D.freshSkips[i]
		d := ""
		if k.Def != "" {
			d = " " + k.Def
		}
		s.Lines = append(s.Lines, fmt.Sprintf("  %s %s %s  fresh %.1f%% (%d holders) %s %.0f%%%s", T12(float64(k.T), false), k.Lane, RuneSlice(k.Mint, 8), k.Pct, k.N, G.Ge, k.Thr, d))
	}
	if len(D.freshSkips) > 15 {
		s.Lines = append(s.Lines, fmt.Sprintf("  … %d more", len(D.freshSkips)-15))
	}
	var nW, nWR int64
	var pW, pPass int64
	for _, f := range fills {
		if f.Fresh.Would {
			nW++
			if f.HasPnl {
				nWR++
				pW += f.Pnl
			}
		} else if f.HasPnl {
			pPass += f.Pnl
		}
	}
	s.Lines = append(s.Lines, fmt.Sprintf("fills checked %d: would skip (log mode / below-threshold lanes) %d, their real P&L %s (%d realized); the others %s", len(fills), nW, lamU(pW, 4), nWR, lamU(pPass, 4)))
	if nW > 0 {
		s.setTone(len(s.Lines)-1, tonePnl(-pW))
	}
	s.JSON.Set("mode", mode).Set("spec", spec).Set("ra_def", def).Set("skips_t2", byLane["T2"]).Set("skips_ra", byLane["RA"]).
		Set("fills", len(fills)).Set("fills_would", nW).Set("pnl_would", pW)
	return s
}

func (A *V5Acc) secFlow(R *V5Report) *D43Section {
	var fills []*V5Fill
	for _, f := range R.Fills {
		if f.Flow != nil {
			fills = append(fills, f)
		}
	}
	if len(fills) == 0 && A.d48.nFlow == 0 {
		return nil
	}
	s := &D43Section{Key: "flow", Title: "FOLLOWER FLOW (dip48 log: outside buys / sells after our fill, SOL)", JSON: &JObj{}}
	hdr := fmt.Sprintf("%-8s %-2s %-8s %6s %6s %6s %6s %6s %6s %6s %6s %9s", "time", "", "mint", "b+1", "s+1", "b+2", "s+2", "bots", "fleet", "retail", "rivals", "P&L "+unitS())
	s.Lines = append(s.Lines, "  "+hdr)
	s.Pre = append(s.Pre, len(s.Lines)-1)
	for i := len(fills) - 1; i >= 0 && len(fills)-1-i < 20; i-- {
		f := fills[i]
		fl := f.Flow
		pnl := G.Dash
		if f.HasPnl {
			pnl = Sol(f.Pnl, true, 4, true)
		}
		s.Lines = append(s.Lines, "  "+fmt.Sprintf("%-8s %-2s %-8s %6.2f %6.2f %6.2f %6.2f %6.2f %6.2f %6.2f %6.2f %9s", T12(float64(f.T), false), f.Kind, RuneSlice(f.Mint, 8),
			fl.B1, fl.S1, fl.B2, fl.S2, fl.Buy1["bots"], fl.Buy1["fleet"], fl.Buy1["retail"], fl.Buy1["rivals"], pnl))
		s.Pre = append(s.Pre, len(s.Lines)-1)
		s.setTone(len(s.Lines)-1, tonePnl(f.Pnl))
	}
	s.Lines = append(s.Lines, "bots / fleet / retail / rivals = buys through +1; b / s = all outside buys / sells through fill+1 / fill+2")
	// the correlation with the result: realized fills split by their +1 buy SOL tercile
	var rf []*V5Fill
	for _, f := range fills {
		if f.HasPnl {
			rf = append(rf, f)
		}
	}
	terc := []any{}
	if len(rf) >= 3 {
		sort.SliceStable(rf, func(i, j int) bool { return rf[i].Flow.B1 < rf[j].Flow.B1 })
		n := len(rf)
		s.Lines = append(s.Lines, fmt.Sprintf("by +1 buy SOL tercile (%d realized fills):", n))
		for k, name := range []string{"low", "mid", "high"} {
			a, b := k*n/3, (k+1)*n/3
			part := rf[a:b]
			var sum int64
			var wins int
			for _, f := range part {
				sum += f.Pnl
				if f.Pnl > 0 {
					wins++
				}
			}
			avg := float64(sum) / float64(max(1, len(part))) / 1e9
			s.Lines = append(s.Lines, fmt.Sprintf("  %-4s b+1 %.2f..%.2f  %d fills  win %d%%  avg %s  sum %s", name, part[0].Flow.B1, part[len(part)-1].Flow.B1, len(part),
				100*wins/max(1, len(part)), solU(avg, 4), lamU(sum, 3)))
			s.setTone(len(s.Lines)-1, tonePnl(sum))
			terc = append(terc, (&JObj{}).Set("tercile", name).Set("lo", PyFloat(part[0].Flow.B1)).Set("hi", PyFloat(part[len(part)-1].Flow.B1)).
				Set("n", len(part)).Set("wins", wins).Set("sum", sum))
		}
	} else {
		s.Lines = append(s.Lines, fmt.Sprintf("by +1 buy SOL tercile: needs 3 realized fills (%d so far)", len(rf)))
	}
	s.JSON.Set("records", A.d48.nFlow).Set("fills", len(fills)).Set("terciles", terc)
	return s
}

func (A *V5Acc) secRival(R *V5Report) *D43Section {
	D := &A.d48
	mode, spec := rawStr(A.fsCur["rival_gate"]), rawStr(A.fsCur["rival_gate_spec"])
	var fills []*V5Fill
	for _, f := range R.Fills {
		if f.Rival != nil {
			fills = append(fills, f)
		}
	}
	if len(D.rivWins) == 0 && len(fills) == 0 && (mode == "" || mode == "off") {
		return nil
	}
	s := &D43Section{Key: "rival_gate", Title: "RIVAL GATE (dip49: T2 tries need slippage rivals, or an old dev; per try, not a pause)", JSON: &JObj{}}
	s.Lines = append(s.Lines, fmt.Sprintf("mode %s · spec %s (withheld when rivals <= R0, or rivals <= R2 and dev age < AGE_H h)", strings.ToUpper(orDash(mode)), orDash(spec)))
	var wWith, wWould, wOpen, wPass, tTries, tWith, tWould int64
	for _, r := range D.rivWins {
		tTries += r.Tries
		tWith += r.Withheld
		tWould += r.Would
		switch {
		case r.Withheld > 0:
			wWith++
		case r.Would > 0:
			wWould++
		case r.Open > 0:
			wOpen++
		default:
			wPass++
		}
	}
	s.Lines = append(s.Lines, fmt.Sprintf("T2 windows %d: all sent %d · withheld (live) %d · would (log) %d · fail-open %d · tries %s, withheld %s, would %s",
		len(D.rivWins), wPass, wWith, wWould, wOpen, IC(tTries), IC(tWith), IC(tWould)))
	for i := len(D.rivWins) - 1; i >= 0 && len(D.rivWins)-1-i < 12; i-- {
		r := D.rivWins[i]
		age := "?"
		if r.HasAge {
			age = devAgeS(r.DevAge)
		}
		s.Lines = append(s.Lines, fmt.Sprintf("  %s w%d %s  rivals min %d · dev age %s (%s) · tries %d withheld %d would %d", T12(float64(r.T), false), r.W, RuneSlice(r.Mint, 8),
			r.RivMin, age, orDash(r.Src), r.Tries, r.Withheld, r.Would))
		if r.Withheld > 0 {
			s.setTone(len(s.Lines)-1, "warn")
		}
	}
	var nB int64
	var pB int64
	for _, f := range fills {
		if f.Rival.Blocked && f.Rival.Open == "" {
			nB++
			if f.HasPnl {
				pB += f.Pnl
			}
		}
	}
	if len(fills) > 0 {
		s.Lines = append(s.Lines, fmt.Sprintf("fills with a verdict %d: would block %d, their real P&L %s", len(fills), nB, lamU(pB, 4)))
	}
	s.JSON.Set("mode", mode).Set("spec", spec).Set("windows", len(D.rivWins)).Set("windows_withheld", wWith).Set("windows_would", wWould).
		Set("tries", tTries).Set("tries_withheld", tWith).Set("fills", len(fills)).Set("fills_block", nB).Set("pnl_block", pB)
	return s
}
