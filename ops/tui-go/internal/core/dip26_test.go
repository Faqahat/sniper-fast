package core

import (
	"bufio"
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
)

// dip26: the live re-arm and the send-path A/B. Real lines of AMS run 38 (dip26_lines_test.go), a real slice of its
// records (testdata/dip26_r38_slice.jsonl: run_start, re-arm windows 90 and 117 and T2 window 118 with every record
// (arm, tries, landings, fill, exit, sell, close, realized, account close), a deferred re-arm window, re-arm / T2
// skips, a T2 QUIET stop), the frozen 38-minute copy against an independent encoding/json scan, and the SEND-PATH
// edges in the engine's format (src/send/mod.rs, src/fast.rs).

func feedRecs(t *testing.T, M *Model, path string) {
	t.Helper()
	b, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var ls [][]byte
	for _, l := range strings.Split(strings.TrimRight(string(b), "\n"), "\n") {
		ls = append(ls, []byte(l))
	}
	M.FeedJSONL(ls)
}

func viewAt(M *Model, now float64, running bool) *View {
	ctx := &Ctx{Src: &Source{Model: M, TJ: NewTail("/nonexistent"), TL: NewTail("/nonexistent")}, Price: NewPrice(100, false),
		AssumeRunning: running, FixedNow: now}
	return BuildView(ctx, -1)
}

func TestDip26Lines(t *testing.T) {
	M := NewModel(0, 100)
	feedStrs(M, r38Live, r38Start, r38PS, r38Status)
	if M.Bad != 0 {
		t.Fatalf("bad lines %d", M.Bad)
	}
	S := M.Sessions[0]
	c := S.RALog
	if c == nil || !c.On || c.Src != "log" || c.Spend != 650_000_000 || c.Gap != 20 || c.Wait != 3 || c.Quiet != "6:2" || c.R5 || !c.HasR5 ||
		c.MaxAge != 141 || c.CurveSol != 100 || c.BigPct != 6 || c.StopMs != 30 {
		t.Fatalf("REARM ON: %+v", c)
	}
	if S.PSCaps != [2]int64{60, 40} {
		t.Fatalf("caps %v", S.PSCaps)
	}
	if r, _ := S.PSL["routes"].(string); r != "default=helius-ps+astralane-ps" {
		t.Fatalf("routes %q", S.PSL["routes"])
	}
	// the REARM part does not leak into the T2 settings (the main line's parse)
	if n, _ := S.PSL["spend"].(Num); n.Int() != 696_000_000 {
		t.Fatalf("T2 spend %v", S.PSL["spend"])
	}
	if n, _ := S.PSL["k"].(Num); n.Int() != 8 {
		t.Fatalf("k %v", S.PSL["k"])
	}
	e := S.RAEng
	if !e.Has || e.Windows != 72 || e.Now != 0 || e.Fills != 20 || e.Realized != 322_300_000 || e.Sells6 != 370 || e.Cands != 281 || e.Checks != 281 ||
		e.Waited != 16 || e.ArmedWait != 9 || e.Pending != 0 || e.Attempts != 4894 || e.Fees != 22_840_000 || e.Closed != 20 {
		t.Fatalf("rearm status: %+v", e)
	}
	if e.Skips.Get("rearm_no_holder") != 183 || e.Skips.Get("rearm_age") != 89 || e.Skips.Len() != 7 || e.Ends.Get("superseded") != 2 || e.Ends.Len() != 6 {
		t.Fatalf("rearm skips / ends: %v / %v", e.Skips.Items(), e.Ends.Items())
	}
	g := S.AB.Eng
	if !g.Has || len(g.Order) != 2 || g.Paths["astralane-ps"] != [7]int64{4312, 27, 3301, 662, 64, 0, 258} || g.Paths["helius-ps"] != [7]int64{4607, 16, 3495, 651, 77, 0, 364} {
		t.Fatalf("per path: %+v", g)
	}
	if g.NotSea.Get("rate_path_config") != 381 || g.NotSea.Get("paused_presend_position") != 156 || g.Acks.Get("200") != 8919 {
		t.Fatalf("not-sent %v acks %v", g.NotSea.Items(), g.Acks.Items())
	}
	// T2's status figures are untouched by the re-arm's part: "fills 43/0" etc. come from the PRESEND LIVE part
	if !S.Status.HasPS || !S.Status.HasFills || S.Status.PSFills != 43 {
		t.Fatalf("T2 status: %+v", S.Status)
	}
	if v := viewAt(M, 0, true); v.Build != "dip26" || !v.RA.On || v.RA.Cfg.Src != "log" {
		t.Fatalf("view: build %s RA %+v", v.Build, v.RA.Cfg)
	}

	// SEND-PATH edges: astralane-ps's lines count like every other path's (UNHEALTHY = an error, RECOVERED = not one)
	for _, p := range []string{"astralane-ps", "helius-ps"} {
		feedStrs(M, "  SEND-PATH "+p+" UNHEALTHY: FAST connection: no answer for 2 s (half-dead): reset, reconnecting (reset #1)")
		if M.PathTotal[p] != 1 || M.PathKind[p] != "unhealthy" || M.PathEdges[p] == nil || !M.PathEdges[p].Down || M.PathEdges[p].Downs != 1 {
			t.Fatalf("%s unhealthy: total %d kind %q edge %+v", p, M.PathTotal[p], M.PathKind[p], M.PathEdges[p])
		}
		feedStrs(M, "  SEND-PATH "+p+" RECOVERED: FAST connection re-established (reconnect #1)")
		if e := M.PathEdges[p]; M.PathTotal[p] != 1 || e.Down || e.Ups != 1 || !strings.Contains(e.Detail, "no answer for 2 s") {
			t.Fatalf("%s recovered: total %d edge %+v", p, M.PathTotal[p], e)
		}
	}
	feedStrs(M, "  SEND-PATH astralane-ps UNHEALTHY: 3 transport errors in a row (last: astralane-ps: error sending request): HTTP client REBUILT (fresh connections, DNS re-resolved; rebuild #1)",
		"  SEND-PATH astralane-ps UNHEALTHY: 3 transport errors in a row (last: astralane-ps: error sending request): HTTP client REBUILT (fresh connections, DNS re-resolved; rebuild #2)")
	if !hasAlert(viewAt(M, 0, true), "astralane-ps unhealthy 3/10m") {
		t.Fatal("3 UNHEALTHY lines in 10 min: no path alert (like the other paths)")
	}
}

// the slice's figures, from an independent scan (tools: oracle26.py on testdata/dip26_r38_slice.jsonl)
func TestDip26Slice(t *testing.T) {
	M := NewModel(0, 100)
	feedStrs(M, r38Live, r38Start, r38PS)
	feedRecs(t, M, filepath.Join("testdata", "dip26_r38_slice.jsonl"))
	if M.Bad != 0 {
		t.Fatalf("bad %d", M.Bad)
	}
	S := M.Sessions[0]
	if S.RS.Rearm == nil || !S.RS.Rearm.On || S.RS.Rearm.Spend != 650_000_000 || S.RS.Rearm.Gap != 20 || S.RS.Rearm.Quiet != "6:2" || !S.RS.Rearm.HasR5 ||
		S.RS.PSMax.Int() != 60 || S.RS.PSPathMax.Int() != 40 {
		t.Fatalf("run_start rearm %+v caps %v %v", S.RS.Rearm, S.RS.PSMax, S.RS.PSPathMax)
	}
	v := viewAt(M, 0, false)
	t2, ra, ps := v.T2, v.RA, v.PS
	if t2.Fills != 1 || t2.Wins != 0 || t2.Real != -34538387 || t2.Rent != 1508820 || t2.Fees != 35840 || t2.FeeN != 7 || t2.Net != -33065407 || t2.Sent != 8 || t2.Armed != 2 {
		t.Fatalf("T2 %+v", t2)
	}
	if !ra.On || ra.Arms != 3 || ra.ArmedWait != 1 || ra.Defers != 1 || ra.Sent != 6 || ra.Fills != 2 || ra.Wins != 2 || ra.Real != 33347653 || ra.Rent != 3017640 ||
		ra.Fees != 20480 || ra.FeeN != 4 || ra.Net != 36344813 {
		t.Fatalf("RA %+v", ra)
	}
	if ra.Skips.Get("rearm_no_holder") != 1 || ra.Skips.Get("rearm_age") != 1 || ra.Skips.Len() != 2 || ra.Ends.Get("expired") != 1 || ra.Ends.Get("filled") != 2 || ra.Ends.Len() != 2 {
		t.Fatalf("RA skips %v ends %v", ra.Skips.Items(), ra.Ends.Items())
	}
	// T2's window counters hold T2's records only (the re-arm's arms / skips / disarms were counted with them before dip26 support)
	if ps.Armed != 2 || ps.Skips.Get("create_slot") != 1 || ps.Skips.Get("quiet") != 1 || ps.Skips.Len() != 2 || ps.Disarms.Get("quiet") != 1 ||
		ps.Disarms.Get("filled") != 1 || ps.Disarms.Len() != 2 || ps.QSkips != 1 || ps.QStops != 1 {
		t.Fatalf("T2 counters: armed %d skips %v disarms %v quiet %d/%d", ps.Armed, ps.Skips.Items(), ps.Disarms.Items(), ps.QSkips, ps.QStops)
	}
	// the money adds up: T2 + re-arm = the run's pre-send; + regular = the run P&L
	if ps.Fills != t2.Fills+ra.Fills || ps.Net != t2.Net+ra.Net || v.Total != t2.Net+ra.Net+v.Reg.Total || ps.Sent != t2.Sent+ra.Sent {
		t.Fatalf("sums: PS %d/%d T2 %d RA %d total %d", ps.Fills, ps.Net, t2.Net, ra.Net, v.Total)
	}
	// the positions: re-arm ones tagged, sized by their own fill record
	var nRA, nT2 int
	for _, tr := range v.Trades {
		switch {
		case tr.Rearm && tr.Spend.Int() == 650_000_000:
			nRA++
		case !tr.Rearm && tr.Spend.Int() == 696_000_000:
			nT2++
		default:
			t.Errorf("trade %s rearm %v spend %d", tr.Mint, tr.Rearm, tr.Spend.Int())
		}
		if tr.Path == "" || PathCode(tr.Path) == "" {
			t.Errorf("trade %s path %q", tr.Mint, tr.Path)
		}
	}
	if nRA != 2 || nT2 != 1 {
		t.Fatalf("trades RA %d T2 %d", nRA, nT2)
	}
	// the A/B
	if !v.AB.On || len(v.AB.Paths) != 2 || v.AB.Spec != "default=helius-ps+astralane-ps" {
		t.Fatalf("AB %+v", v.AB)
	}
	s := ABOf(v.Sessions, v.Trades, M, v.NowNS())
	want := map[string]struct {
		sent, land, landed, seen, same, ack200, fills, pos, wins, pnl int64
		p50, p90                                                      float64
	}{"helius-ps": {7, 7, 7, 7, 5, 7, 1, 1, 1, 4355975, 56.4, 81.5}, "astralane-ps": {7, 7, 7, 7, 5, 7, 2, 2, 1, -5546709, 51.6, 95.6}}
	if len(s.Rows) != 2 || !s.Rule || s.MaxPerSec != 60 || s.PathMaxPerSec != 40 {
		t.Fatalf("summary %+v", s)
	}
	for _, r := range s.Rows {
		w := want[r.Path]
		if r.Sent != w.sent || r.Land != w.land || r.Landed != w.landed || r.Seen != w.seen || r.Same != w.same || r.Ack200 != w.ack200 || r.AckFail() != 0 ||
			r.Fills != w.fills || r.Pos != w.pos || r.Wins != w.wins || r.Pnl != w.pnl || r.Refused != 0 {
			t.Errorf("%s: %+v", r.Path, r)
		}
		if math.Abs(r.P50-w.p50) > 0.1 || math.Abs(r.P90-w.p90) > 0.1 {
			t.Errorf("%s p50/p90 %.2f/%.2f, want %.1f/%.1f", r.Path, r.P50, r.P90, w.p50, w.p90)
		}
	}
	// config, snapshot, JSON
	if it := v.ItemByKey("rearm"); it == nil || it.Short != "RA 0.65 g20 q6:2" || !strings.Contains(it.Full, "QUIET stop 6:2") {
		t.Fatalf("rearm item %+v", it)
	}
	if it := v.ItemByKey("ab"); it == nil || it.Short != "A/B HL/AS" {
		t.Fatalf("ab item %+v", it)
	}
	ctx := &Ctx{Src: &Source{Model: M, TJ: NewTail("/x"), TL: NewTail("/x")}}
	txt := SnapshotText(v, ctx, 200)
	for _, w := range []string{"pre-send  -0.0331 SOL", "T2: 1 fills, 0 wins | realized -0.0345, rent back +0.0015, failed tries -0.0000 (7 x 5,120)",
		"re-arm    +0.0363 SOL", "2 fills, 2 wins | realized +0.0333, rent back +0.0030", "re-arm    config 0.650 SOL",
		"no_holder 1", "age 1", "ends: filled 2", "A/B       routes default=helius-ps+astralane-ps (the tries alternate), caps 60/s, 40/s a path",
		"helius-ps     7 tries, refused 0 (0.0%), landed 100%, same slot 71%", "RA ", " via AS", " via HL"} {
		if !strings.Contains(txt, w) {
			t.Errorf("snapshot lacks %q:\n%s", w, txt)
		}
	}
	j := SnapshotJSON(v, ctx, nil)
	for _, w := range []string{`"dip26": {`, `"t2": {`, `"rearm": {`, `"ab": {`, `"net": 36344813`, `"refused": 0`, `"routes": "default=helius-ps+astralane-ps"`} {
		if !strings.Contains(j, w) {
			t.Errorf("json lacks %q", w)
		}
	}
	// the presend object keeps the whole pre-send (its money adds up with regular to total_lamports)
	var jo map[string]any
	if err := json.Unmarshal([]byte(j), &jo); err != nil {
		t.Fatal(err)
	}
	pso := jo["presend"].(map[string]any)
	if int64(pso["net"].(float64))+int64(jo["regular"].(map[string]any)["total"].(float64)) != int64(jo["total_lamports"].(float64)) || int64(pso["armed"].(float64)) != 2 {
		t.Fatalf("presend JSON %v", pso)
	}
}

// TestDip26Gaps: the refused ticks are inferred per path from a window's missing tick numbers (the engine's route rule
// path = paths[(n + w) % 2]): a single missing tick is that path's refusal; a run of >= 2 a pause of every path. The
// alert: a path refusing > 1% of its tries in the last 10 minutes.
func TestDip26Gaps(t *testing.T) {
	b, err := os.ReadFile(filepath.Join("testdata", "dip26_r38_slice.jsonl"))
	if err != nil {
		t.Fatal(err)
	}
	var rs, att string
	for _, l := range strings.Split(string(b), "\n") {
		if strings.Contains(l, `"ev":"run_start"`) {
			rs = l
		}
		if att == "" && strings.Contains(l, `"ev":"presend_attempt"`) && !strings.Contains(l, `"kind"`) {
			att = l // a real T2 try (window 118)
		}
	}
	var a0 map[string]any
	if json.Unmarshal([]byte(att), &a0) != nil || rs == "" {
		t.Fatal("slice")
	}
	w0, n0, t0 := int64(a0["w"].(float64)), int64(a0["n"].(float64)), int64(a0["t"].(float64))
	tryAt := func(w, n int64) []byte {
		x := strings.Replace(att, `"n":`+strconv.FormatInt(n0, 10)+`,`, `"n":`+strconv.FormatInt(n, 10)+`,`, 1)
		x = strings.Replace(x, `"w":`+strconv.FormatInt(w0, 10)+`,`, `"w":`+strconv.FormatInt(w, 10)+`,`, 1)
		path := map[int64]string{0: "helius-ps", 1: "astralane-ps"}[(n+w)%2]
		x = strings.Replace(x, `"path":"helius-ps"`, `"path":"`+path+`"`, 1)
		x = strings.Replace(x, `"path":"astralane-ps"`, `"path":"`+path+`"`, 1)
		return []byte(x)
	}
	M := NewModel(0, 100)
	var ls [][]byte
	ls = append(ls, []byte(rs))
	// window 1000: ticks 1 2 4 5 8 9 sent: 3 refused alone (path (3 + 1000) % 2 = astralane-ps), 6 7 a pause (one of each)
	for _, n := range []int64{1, 2, 4, 5, 8, 9} {
		ls = append(ls, tryAt(1000, n))
	}
	// window 1001: its first tick is 3 (ticks 1 and 2 missing: a pause), then every tick to 60 (58 written)
	for n := int64(3); n <= 60; n++ {
		ls = append(ls, tryAt(1001, n))
	}
	M.FeedJSONL(ls)
	a := M.Sessions[0].AB
	h, as := a.Paths["helius-ps"], a.Paths["astralane-ps"]
	if !a.On || h == nil || as == nil || as.Refused != 1 || h.Refused != 0 || as.Gapped+h.Gapped != 4 || as.Gapped != 2 || h.Gapped != 2 || h.Sent+as.Sent != 64 {
		t.Fatalf("refused %d/%d gapped %d/%d sent %d/%d", h.Refused, as.Refused, h.Gapped, as.Gapped, h.Sent, as.Sent)
	}
	// the last 10 minutes: astralane-ps 1 refused of 33 ticks = 3% > 1%: the alert (running runs only)
	v := viewAt(M, float64(t0)/1e9+60, true)
	if !hasAlert(v, "astralane-ps refused 3.0% of its tries in 10 min (1 of 33)") || hasAlert(v, "helius-ps refused") {
		t.Fatalf("alerts %+v", v.Alerts)
	}
	if v := viewAt(M, float64(t0)/1e9+20*60, true); hasAlert(v, "refused") {
		t.Fatalf("20 min later: %+v", v.Alerts)
	}
	if v := viewAt(M, float64(t0)/1e9+60, false); hasAlert(v, "refused") {
		t.Fatal("an ended run alerts")
	}
}

// TestDip26R38: the frozen 38-minute copy of run 38 against an independent encoding/json scan of its records: the T2 /
// re-arm money and counters, every A/B figure per path (refused ticks by the same rule, from the decoded records), the
// fills and P&L by fill path.
func TestDip26R38(t *testing.T) {
	p := filepath.Join(func() string {
		if d := os.Getenv("DIPMON_DIP26_DATA"); d != "" {
			return d
		}
		return "/home/moiz/sniper-data/tui/runs-dip26"
	}(), "ams/runs/dip_ams_r38.jsonl")
	if _, err := os.Stat(p); err != nil {
		t.Skip("no frozen r38: " + p)
	}
	src := NewSource(p, "", 0, 100)
	src.LoadAll(LoadChunk, 0, nil)
	M := src.Model
	ctx := &Ctx{Src: src, Price: NewPrice(100, false), AssumeRunning: true, FixedNow: 1793309906}
	v := BuildView(ctx, -1)
	// the independent scan
	type money struct{ fills, wins, nreal, real, rent, fees, feen, sent, arms int64 }
	var T2, RA money
	raSk, raEnd, t2Sk, t2Dis := map[string]int64{}, map[string]int64{}, map[string]int64{}, map[string]int64{}
	var defers, armedWait int64
	type pth struct{ sent, land, landed, seen, same, ack200, ackOther, fills, refused, gapped int64 }
	paths := map[string]*pth{}
	s2r := map[string][]float64{}
	pp := func(k string) *pth {
		if paths[k] == nil {
			paths[k] = &pth{}
		}
		return paths[k]
	}
	ticks := map[int64]map[int64]bool{}
	var routes []string
	posPath := map[string]string{}
	posRA := map[string]bool{}
	var posOrder []string
	realBy := map[string]int64{}
	var atas []struct {
		mint string
		d    int64
	}
	f, _ := os.Open(p)
	defer f.Close()
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1<<20), 16<<20)
	for sc.Scan() {
		var o map[string]any
		if json.Unmarshal(sc.Bytes(), &o) != nil {
			continue
		}
		ev, _ := o["ev"].(string)
		kind, _ := o["kind"].(string)
		ra := kind == "rearm"
		m := &T2
		if ra {
			m = &RA
		}
		num := func(k string) int64 { x, _ := o[k].(float64); return int64(x) }
		str := func(k string) string { x, _ := o[k].(string); return x }
		key := strconv.FormatInt(num("w"), 10) + "|" + str("mint")
		switch ev {
		case "run_start":
			r := o["presend_live"].(map[string]any)["routes"].(string)
			routes = strings.Split(strings.SplitN(r, "=", 2)[1], "+")
		case "presend_live_arm":
			m.arms++
			if ra && o["deferred"] != nil {
				armedWait++
			}
		case "presend_live_skip":
			if ra {
				raSk[str("why")]++
			} else {
				t2Sk[str("why")]++
			}
		case "presend_live_disarm":
			if ra {
				raEnd[str("why")]++
			} else {
				t2Dis[str("why")]++
			}
		case "presend_live_rearm_defer":
			defers++
		case "presend_attempt":
			if d, _ := o["dry"].(bool); d {
				continue
			}
			m.sent++
			pp(str("path")).sent++
			if ticks[num("w")] == nil {
				ticks[num("w")] = map[int64]bool{}
			}
			ticks[num("w")][num("n")] = true
		case "presend_attempt_land":
			x := pp(str("path"))
			x.land++
			if str("res") != "unseen" {
				x.landed++
			}
			if ms, ok := o["ms_send_to_rx"].(float64); ok {
				x.seen++
				s2r[str("path")] = append(s2r[str("path")], ms)
				if sa, ok := o["slots_after_send"].(float64); ok && sa == 0 {
					x.same++
				}
			}
			if a, ok := o["ack"].(float64); ok && a == 200 {
				x.ack200++
			} else {
				x.ackOther++
			}
			if str("res") != "ok" && num("fee") != 0 {
				m.fees += num("fee")
				m.feen++
			}
		case "presend_live_fill":
			m.fills++
			pp(str("path")).fills++
			if _, ok := posPath[key]; !ok {
				posPath[key], posRA[key] = str("path"), ra
				posOrder = append(posOrder, key)
			}
		case "presend_live_close":
			if str("path") != "" {
				posPath[key] = str("path")
			}
		case "presend_live_realized":
			m.nreal++
			if pn, ok := o["pnl"].(float64); ok {
				m.real += int64(pn)
				if pn > 0 {
					m.wins++
				}
				realBy[key] = int64(pn)
			}
		case "presend_live_ata_close":
			if ok, isB := o["ok"].(bool); isB && !ok {
				continue
			}
			atas = append(atas, struct {
				mint string
				d    int64
			}{str("mint"), num("delta")})
		}
	}
	// rent back: each closed account to the first position of its mint without rent yet (the positions close in order)
	done := map[string]bool{}
	var t2Rent, raRent int64
	for _, a := range atas {
		hit := ""
		for _, k := range posOrder {
			if strings.HasSuffix(k, "|"+a.mint) && !done[k] {
				hit = k
				break
			}
		}
		switch {
		case hit == "":
			t2Rent += a.d
		case posRA[hit]:
			done[hit] = true
			raRent += a.d
		default:
			done[hit] = true
			t2Rent += a.d
		}
	}
	// refused ticks: the same rule from the decoded tries
	for w, ns := range ticks {
		var mx int64
		for n := range ns {
			mx = max(mx, n)
		}
		run := int64(0)
		for n := int64(1); n <= mx+1; n++ {
			if n <= mx && !ns[n] {
				run++
				continue
			}
			if run > 0 {
				for k := n - run; k < n; k++ {
					q := pp(routes[(k+w)%int64(len(routes))])
					if run == 1 {
						q.refused++
					} else {
						q.gapped++
					}
				}
				run = 0
			}
		}
	}
	// compare
	t2, ra := v.T2, v.RA
	if t2.Fills != T2.fills || t2.Wins != T2.wins || t2.NReal != T2.nreal || t2.Real != T2.real || t2.Fees != T2.fees || t2.FeeN != T2.feen || t2.Sent != T2.sent || t2.Armed != T2.arms {
		t.Errorf("T2 %+v\n want %+v", t2, T2)
	}
	if ra.Fills != RA.fills || ra.Wins != RA.wins || ra.NReal != RA.nreal || ra.Real != RA.real || ra.Fees != RA.fees || ra.FeeN != RA.feen || ra.Sent != RA.sent ||
		ra.Arms != RA.arms || ra.Defers != defers || ra.ArmedWait != armedWait {
		t.Errorf("RA %+v\n want %+v defers %d waited %d", ra, RA, defers, armedWait)
	}
	if t2.Rent != t2Rent || ra.Rent != raRent || t2.Rent+ra.Rent != v.PS.Rent || t2.Net+ra.Net != v.PS.Net || ra.Net != ra.Real+ra.Rent-ra.Fees {
		t.Errorf("rent T2 %d RA %d, want %d / %d (all %d)", t2.Rent, ra.Rent, t2Rent, raRent, v.PS.Rent)
	}
	for k, n := range raSk {
		if ra.Skips.Get(k) != n {
			t.Errorf("RA skip %s %d, want %d", k, ra.Skips.Get(k), n)
		}
	}
	for k, n := range raEnd {
		if ra.Ends.Get(k) != n {
			t.Errorf("RA end %s %d, want %d", k, ra.Ends.Get(k), n)
		}
	}
	for k, n := range t2Sk {
		if v.PS.Skips.Get(k) != n {
			t.Errorf("T2 skip %s %d, want %d", k, v.PS.Skips.Get(k), n)
		}
	}
	if v.PS.Skips.Len() != len(t2Sk) || v.PS.Disarms.Len() != len(t2Dis) || ra.Skips.Len() != len(raSk) || ra.Ends.Len() != len(raEnd) {
		t.Errorf("counter keys: T2 %v %v RA %v %v", v.PS.Skips.Items(), v.PS.Disarms.Items(), ra.Skips.Items(), ra.Ends.Items())
	}
	for k, n := range t2Dis {
		if v.PS.Disarms.Get(k) != n {
			t.Errorf("T2 disarm %s %d, want %d", k, v.PS.Disarms.Get(k), n)
		}
	}
	s := ABOf(v.Sessions, v.Trades, M, v.NowNS())
	if len(s.Rows) != len(paths) {
		t.Fatalf("rows %d, paths %d", len(s.Rows), len(paths))
	}
	pnl, pos := map[string]int64{}, map[string]int64{}
	for k, x := range realBy {
		if pa := posPath[k]; pa != "" {
			pnl[pa] += x
			pos[pa]++
		}
	}
	for _, r := range s.Rows {
		w := paths[r.Path]
		if r.Sent != w.sent || r.Land != w.land || r.Landed != w.landed || r.Seen != w.seen || r.Same != w.same || r.Ack200 != w.ack200 ||
			r.AckFail() != w.ackOther || r.Fills != w.fills || r.Refused != w.refused || r.Gapped != w.gapped || r.Pnl != pnl[r.Path] || r.Pos != pos[r.Path] {
			t.Errorf("%s: %+v\n want %+v pnl %d pos %d", r.Path, r, *w, pnl[r.Path], pos[r.Path])
		}
		h := &Hist{}
		for _, x := range s2r[r.Path] {
			h.Add(x)
		}
		histClose(t, r.Path+" send->land", h, s2r[r.Path])
		if q, _ := h.Quantiles(0.5, 0.9); math.Abs(q[0]-r.P50) > 1e-9 || math.Abs(q[1]-r.P90) > 1e-9 {
			t.Errorf("%s: p50/p90 %v/%v, hist %v", r.Path, r.P50, r.P90, q)
		}
	}
	if paths["astralane-ps"].refused == 0 || v.Build != "dip26" {
		t.Errorf("the frozen copy has astralane-ps refusals (%d) and is dip26 (%s)", paths["astralane-ps"].refused, v.Build)
	}
}

// TestNoDip26OnOldLines: dip24 / dip20 runs get none of it (no re-arm, no A/B, no items, no JSON, the build as before).
func TestNoDip26OnOldLines(t *testing.T) {
	M := NewModel(0, 100)
	feedStrs(M, append(append([]string{}, r36Start...), r36Status)...)
	v := d24View(M, true)
	if v.RA.On || v.AB.On || v.Build != "dip24" || M.Sessions[0].RALog != nil {
		t.Fatalf("RA %v AB %v build %s", v.RA.On, v.AB.On, v.Build)
	}
	for _, k := range []string{"rearm", "ab"} {
		if v.ItemByKey(k) != nil {
			t.Fatalf("item %s on a dip24 log", k)
		}
	}
	ctx := &Ctx{Src: &Source{Model: M, TJ: NewTail("/x"), TL: NewTail("/x")}}
	if strings.Contains(SnapshotJSON(v, ctx, nil), "dip26") || strings.Contains(SnapshotText(v, ctx, 200), "re-arm    ") {
		t.Fatal("dip26 output on a dip24 log")
	}
	// T2 = PS exactly without the re-arm
	if v.T2.Net != v.PS.Net || v.T2.Fills != v.PS.Fills || v.T2.Exits != v.PS.Exits {
		t.Fatal("T2 differs from the pre-send figures without re-arm")
	}
}

// BenchmarkABOfR38: the A/B summary of the frozen r38 (the Pre-send tab rebuilds it when the records move).
func BenchmarkABOfR38(b *testing.B) {
	p := "/home/moiz/sniper-data/tui/runs-dip26/ams/runs/dip_ams_r38.jsonl"
	if _, err := os.Stat(p); err != nil {
		b.Skip("no frozen r38")
	}
	src := NewSource(p, "", 0, 100)
	src.LoadAll(LoadChunk, 0, nil)
	v := BuildView(&Ctx{Src: src, Price: NewPrice(100, false), AssumeRunning: true, FixedNow: 1793309906}, -1)
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		ABOf(v.Sessions, v.Trades, src.Model, v.NowNS())
	}
}

// BenchmarkBuildViewR38: the whole view of the frozen r38 (built every refresh).
func BenchmarkBuildViewR38(b *testing.B) {
	p := "/home/moiz/sniper-data/tui/runs-dip26/ams/runs/dip_ams_r38.jsonl"
	if _, err := os.Stat(p); err != nil {
		b.Skip("no frozen r38")
	}
	src := NewSource(p, "", 0, 100)
	src.LoadAll(LoadChunk, 0, nil)
	ctx := &Ctx{Src: src, Price: NewPrice(100, false), AssumeRunning: true, FixedNow: 1793309906}
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		BuildView(ctx, -1)
	}
}
