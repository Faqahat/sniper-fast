package ui

import (
	"fmt"
	"strings"

	"github.com/charmbracelet/x/ansi"

	"dipmon/internal/core"
)

// The config, in five blocks (the overview's CONFIG and the Config tab): what pre-send does, what the regular bot does,
// how the buys are sent, what stops the run, and the QUIET filter / the paper copy.
var cfgBlockTitles = []string{"PRE-SEND", "REGULAR", "ROUTES & SENDING", "SAFETY & LIMITS", "QUIET & PAPER"}
var cfgBlockShort = []string{"PRE-SEND", "REGULAR", "SENDING", "LIMITS", "QUIET"}

// cfgBlockKeys: the config items (core.CfgItem keys) of each block, in order.
var cfgBlockKeys = [][]string{
	{"ps"},
	{"reg", "guard", "m2", "dev"},
	{"routes", "sellfan", "nonce", "near", "skipcl"},
	{"kill", "planned", "build"},
	{"qstop", "qskip", "quiet", "paper"},
}

// blockOf: the block of a config item (unknown items: the limits block, so nothing is ever dropped).
func blockOf(key string) int {
	for i, ks := range cfgBlockKeys {
		for _, k := range ks {
			if k == key {
				return i
			}
		}
	}
	return 3
}

// cfgLine is one line of a block in its long and short forms.
type cfgLine struct{ long, short string }

type cfgBlock struct {
	title, short string
	lines        []cfgLine
}

// cfgBlocks: the overview's config, every field it showed before, grouped.
func (m *Model) cfgBlocks() []cfgBlock {
	t := m.th
	v := m.view
	S := v.S
	pc := v.PSCfg
	sep := t.Dim.Render(" " + m.g("·", "|") + " ")
	dot := func(st string) string { return t.StateDot(st, m.ascii) }
	it := func(k string) *core.CfgItem { return v.ItemByKey(k) }
	num := func(k string) (core.Num, bool) {
		n, ok := pc[k].(core.Num)
		return n, ok && n.Ok()
	}
	minus := m.g("−", "-")
	tpsl := func(tp float64, tpOK bool, sl float64, slots string) cfgLine {
		tps := "off"
		if tpOK {
			tps = "+" + core.F(tp, 0) + "%"
		}
		return cfgLine{t.Val.Render("exit TP " + tps + " / SL " + minus + core.F(sl, 0) + "% / " + slots + " slots"),
			t.Val.Render("TP " + tps + " SL " + minus + core.F(sl, 0) + "% " + slots + "sl")}
	}
	same := func(s string) cfgLine { return cfgLine{s, s} }
	var B []cfgBlock
	add := func(i int, ls ...cfgLine) {
		B = append(B, cfgBlock{cfgBlockTitles[i], cfgBlockShort[i], ls})
	}

	// pre-send
	ps := it("ps")
	psOn := ps != nil && ps.State != "off"
	if !psOn {
		add(0, same(dot("off")+t.Lbl.Render(" off")))
	} else {
		tpN, tpOK := num("tp")
		tp := tpN.Float()
		if tpOK && tp < 1 {
			tp *= 100
		}
		slN, _ := num("sl")
		sl := slN.Float()
		if sl < 1 {
			sl *= 100
		}
		slots, k, spend := "?", "?", "?"
		if n, ok := num("exit_slots"); ok {
			slots = n.Repr()
		}
		if n, ok := num("k"); ok {
			k = n.Repr()
		}
		if n, ok := num("spend"); ok {
			spend = core.F(n.Float()/core.LAM, 2)
		}
		ls := []cfgLine{
			{dot(ps.State) + t.Val.Render(" "+spend+" SOL") + sep + t.Val.Render(k+" tries/slot"),
				dot(ps.State) + t.Val.Render(" "+spend) + sep + t.Val.Render(k+"/slot")},
			tpsl(tp, tpOK && tpN.Truthy(), sl, slots),
		}
		if v.PSStopped != "" {
			ls = append(ls, cfgLine{t.Warn.Render("stopped: " + v.PSStopped), t.Warn.Render("stopped")})
		}
		add(0, ls...)
	}

	// regular
	{
		spend := S.RS.Spend
		if !spend.Truthy() && S.Live.HasSpend {
			spend = core.IntNum(S.Live.Spend)
		}
		tp, tpOK := 0.0, false
		if S.RS.TP.Ok() {
			if S.RS.TP.Float() < 99 {
				tp, tpOK = S.RS.TP.Float()*100, true
			}
		} else if S.Live.HasTP && S.Live.TP != "off" {
			var f float64
			if _, err := fmt.Sscanf(strings.Trim(S.Live.TP, "+%"), "%g", &f); err == nil {
				tp, tpOK = f, true
			}
		}
		sl := 0.0
		if S.RS.SL.Ok() {
			sl = S.RS.SL.Float() * 100
		} else if S.Live.HasSL {
			sl = S.Live.SL
		}
		hold := "?"
		if S.RS.HoldSlots.Truthy() {
			hold = S.RS.HoldSlots.Repr()
		} else if S.Live.HasHold {
			hold = fmt.Sprint(S.Live.Hold)
		}
		guard := S.RS.Guard.Float()
		if !S.RS.Guard.Truthy() && S.Live.HasGuard {
			guard = S.Live.Guard
		}
		rstate := "na"
		switch {
		case v.Cur.KillSet || v.Status == "STOPPING":
			rstate = "part"
		case v.Status == "RUNNING" || v.Status == "WAITING":
			rstate = "on"
		}
		pre := ""
		if rstate != "na" {
			pre = dot(rstate) + " "
		}
		sp := "?"
		if spend.Ok() {
			sp = core.F(spend.Float()/core.LAM, 2)
		}
		l1 := cfgLine{pre + t.Val.Render(sp+" SOL"), pre + t.Val.Render(sp)}
		if guard > 0 {
			l1.long += sep + t.Val.Render("guard +"+core.F((guard-1)*100, 0)+"%")
			l1.short += sep + t.Val.Render("+"+core.F((guard-1)*100, 0)+"%")
		}
		ls := []cfgLine{l1, tpsl(tp, tpOK, sl, hold)}
		var lg, sh []string
		for _, kl := range [][2]string{{"m2", "M2 gate"}, {"dev", "Dev list"}} {
			x := it(kl[0])
			if x == nil {
				continue
			}
			s := t.Lbl.Render(kl[1]+" ") + dot(x.State)
			ss := t.Lbl.Render(strings.Fields(kl[1])[0]+" ") + dot(x.State)
			if kl[0] == "dev" && x.State == "on" {
				d := t.Val.Render(" " + strings.TrimPrefix(x.Short, "dev "))
				s += d
				ss += d
			}
			if kl[0] == "m2" && x.State != "off" && x.Short != "M2 gate" {
				s += t.Val.Render(" " + strings.TrimPrefix(x.Short, "M2 "))
			}
			lg, sh = append(lg, s), append(sh, ss)
		}
		if len(lg) > 0 {
			ls = append(ls, cfgLine{strings.Join(lg, sep), strings.Join(sh, sep)})
		}
		add(1, ls...)
	}

	// routes & sending
	{
		var ls []cfgLine
		l1 := cfgLine{}
		if x := it("routes"); x != nil {
			l1 = cfgLine{t.Lbl.Render("routes ") + t.Val.Render(x.Short), t.Val.Render(x.Short)}
		}
		if x := it("near"); x != nil && x.State == "on" {
			n := strings.TrimPrefix(x.Short, "near ")
			if l1.long != "" {
				l1.long += sep
				l1.short += sep
			}
			l1.long += t.Lbl.Render("near leaders ") + t.Val.Render(n)
			l1.short += t.Lbl.Render("near ") + t.Val.Render(n)
		}
		if l1.long != "" {
			ls = append(ls, l1)
		}
		l2 := cfgLine{}
		if x := it("sellfan"); x != nil {
			l2 = cfgLine{t.Lbl.Render("sell fan-out ") + dot(x.State), t.Lbl.Render("fan ") + dot(x.State)}
		}
		if x := it("nonce"); x != nil {
			n := t.Lbl.Render("nonce ") + dot(x.State)
			if x.State == "on" {
				n += t.Val.Render(" " + strings.TrimPrefix(x.Short, "nonce "))
			}
			if l2.long != "" {
				l2.long += sep
				l2.short += sep
			}
			l2.long += n
			l2.short += n
		}
		if l2.long != "" {
			ls = append(ls, l2)
		}
		if x := it("skipcl"); x != nil {
			ls = append(ls, same(t.Lbl.Render("skip ")+t.Val.Render(strings.ReplaceAll(x.Full, "rakurai", "Rakurai"))))
		}
		if len(ls) == 0 {
			ls = append(ls, same(t.Lbl.Render(core.G.Dash)))
		}
		add(2, ls...)
	}

	// safety & limits
	{
		var ls []cfgLine
		l1 := cfgLine{}
		if v.HasKillLevel {
			k := t.Val.Render(core.F(float64(v.KillLevel)/core.LAM, 3))
			l1 = cfgLine{t.Lbl.Render("kill switch ") + k, t.Lbl.Render("kill ") + k}
		}
		if v.Planned.Truthy() {
			p := t.Val.Render(core.HMS(v.Planned.Float()*60, true, false))
			if l1.long != "" {
				l1.long += sep
				l1.short += sep
			}
			l1.long += t.Lbl.Render("planned ") + p
			l1.short += t.Lbl.Render("plan ") + p
		}
		if l1.long != "" {
			ls = append(ls, l1)
		}
		if psOn {
			var sf, sfee int64
			if S.PSRec {
				sf, sfee = S.PSFills, S.PSFees()
			} else {
				sf, sfee = int64(len(S.LogPSReal)), S.LogPSFees
			}
			capS := "?"
			if n, ok := num("max_fills"); ok && n.Truthy() {
				capS = n.Repr()
			}
			bud := 0.0
			if n, ok := num("fee_budget"); ok && n.Truthy() {
				bud = n.Float()
			}
			fs := t.Val
			if bud > 0 && float64(sfee) > 0.8*bud {
				fs = t.Warn
			}
			fees := fs.Render(core.F(float64(sfee)/core.LAM, 2) + "/" + core.F(bud/core.LAM, 2))
			ls = append(ls, cfgLine{t.Lbl.Render("fills ") + t.Val.Render(fmt.Sprintf("%d/%s", sf, capS)) + sep + t.Lbl.Render("fees ") + fees,
				t.Val.Render(fmt.Sprintf("%d/%s", sf, capS)) + sep + t.Lbl.Render("fee ") + fees})
		}
		ls = append(ls, same(t.Lbl.Render("engine ")+t.Val.Render(v.Build)))
		add(3, ls...)
	}

	// QUIET & paper
	{
		var ls []cfgLine
		q := v.Quiet
		if !q.Present {
			ls = append(ls, cfgLine{t.Lbl.Render("QUIET ") + dot("off") + t.Lbl.Render(" off (not in this engine)"), t.Lbl.Render("QUIET ") + dot("off") + t.Lbl.Render(" off")})
		} else {
			stopOn := q.HasStop && q.Stop != "" && q.Stop != "off"
			n, mm := "?", "?"
			if stopOn && strings.Contains(q.Stop, ":") {
				p := strings.SplitN(q.Stop, ":", 2)
				n, mm = p[0], p[1]
			}
			st := "off"
			if stopOn {
				st = "on"
			}
			l := cfgLine{t.Lbl.Render("stop ") + dot(st), t.Lbl.Render("stop ") + dot(st)}
			if stopOn {
				l.long += t.Val.Render(" " + n + " slots, < " + mm + " trades")
				l.short += t.Val.Render(" " + n + ":" + mm)
			}
			ls = append(ls, l)
			skip := map[string]string{"on": "on", "warm-up": "part"}[q.State]
			if skip == "" {
				skip = "off"
			}
			l = same(t.Lbl.Render("skip ") + dot(skip))
			if q.State == "warm-up" && q.HasOnAt {
				l.long += t.Warn.Render(" on " + core.T12(float64(q.OnAt), false))
				l.short = l.long
			}
			ls = append(ls, l)
		}
		if x := it("paper"); x != nil {
			ls = append(ls, same(t.Lbl.Render("paper ")+dot(x.State)))
		}
		add(4, ls...)
	}
	return B
}

// configBlocks lays the blocks out at width w: side by side (each column's title over it, a rule to the column's
// end; long forms where they fit, else short), or one block a line (title, then its lines joined) when the columns do
// not fit. panel: inside the CONFIG panel (the titles are plain); else the titles row is the section's rule.
// Cached until the items, the size or the theme change.
func (m *Model) configBlocks(w int, panel bool) []string {
	var kb strings.Builder
	fmt.Fprintf(&kb, "%d|%v|%v|%v|%s|%s|", w, panel, m.dark, m.ascii, m.view.Status, m.view.Build)
	for _, it := range m.view.CfgItems {
		kb.WriteString(it.State + it.Short + "|")
	}
	if m.view.Quiet.HasOnAt {
		fmt.Fprintf(&kb, "%d", m.view.Quiet.OnAt)
	}
	S := m.view.S
	fmt.Fprintf(&kb, "|%d|%d|%d|%d|%s", S.PSFills, S.PSFees(), len(S.LogPSReal), S.LogPSFees, m.view.PSStopped)
	key := kb.String()
	if c, ok := m.cfgCache[key]; ok {
		return c.lines
	}
	out := m.configBlocksRaw(w, panel)
	if len(m.cfgCache) > 16 {
		m.cfgCache = map[string]cfgCached{}
	}
	m.cfgCache[key] = cfgCached{out, 0}
	return out
}

type cfgCached struct {
	lines []string
	cols  int
}

func (m *Model) configBlocksRaw(w int, panel bool) []string {
	t := m.th
	B := m.cfgBlocks()
	nb := len(B)
	gap := 3
	hr := m.g("─", "-")
	// side by side: each column long or short (the subset that fits with the most long columns)
	shortW := make([]int, nb)
	longW := make([]int, nb)
	rows := 0
	for k, b := range B {
		tw := ansi.StringWidth(b.title)
		shortW[k], longW[k] = ansi.StringWidth(b.short), tw
		for _, l := range b.lines {
			shortW[k] = max(shortW[k], ansi.StringWidth(l.short))
			longW[k] = max(longW[k], ansi.StringWidth(l.long), shortW[k])
		}
		rows = max(rows, len(b.lines))
	}
	best, bestN := -1, -1
	for mask := 0; mask < 1<<nb; mask++ {
		total, n := gap*(nb-1), 0
		for k := 0; k < nb; k++ {
			if mask&(1<<k) != 0 {
				total += longW[k]
				n++
			} else {
				total += shortW[k]
			}
		}
		if total <= w && n > bestN {
			best, bestN = mask, n
		}
	}
	if best >= 0 {
		widths := make([]int, nb)
		long := make([]bool, nb)
		total := gap * (nb - 1)
		for k := 0; k < nb; k++ {
			long[k] = best&(1<<k) != 0
			widths[k] = shortW[k]
			if long[k] {
				widths[k] = longW[k]
			}
			total += widths[k]
		}
		if spare := w - total; spare > 0 { // share the spare room: the blocks spread over the whole width
			// (first: room for the last block's full title, which takes the rest of the line)
			if need := ansi.StringWidth(B[nb-1].title) - widths[nb-1]; need > 0 {
				spare -= min(need, spare)
			}
			for k := 0; k < nb-1; k++ {
				widths[k] += spare / nb
			}
		}
		var out []string
		var hb strings.Builder
		for k, b := range B {
			title := b.title
			room := widths[k]
			if k == nb-1 {
				room = w - ansi.StringWidth(hb.String())
				if !panel {
					room -= 2 // " ─"
				}
			}
			if ansi.StringWidth(b.title) > room {
				title = b.short
			}
			cw := widths[k]
			if k < nb-1 {
				cw += gap
			} else {
				cw = max(ansi.StringWidth(title), w-ansi.StringWidth(hb.String()))
			}
			seg := t.AccB.Render(title)
			if panel {
				seg = fitLine(seg, cw)
			} else {
				n := cw - ansi.StringWidth(title) - 1
				if k < nb-1 {
					n -= 2 // a gap before the next title
				}
				seg += " " + t.Rule.Render(strings.Repeat(hr, max(0, n)))
				if k < nb-1 {
					seg += "  "
				}
			}
			hb.WriteString(seg)
		}
		out = append(out, cut(hb.String(), w))
		for r := 0; r < rows; r++ {
			var l strings.Builder
			for k, b := range B {
				c := ""
				if r < len(b.lines) {
					c = b.lines[r].short
					if long[k] {
						c = b.lines[r].long
					}
				}
				if k < nb-1 {
					l.WriteString(fitLine(c, widths[k]) + strings.Repeat(" ", gap))
				} else {
					l.WriteString(cut(c, max(1, w-ansi.StringWidth(l.String()))))
				}
			}
			out = append(out, l.String())
		}
		return out
	}
	// one block a line: "PRE-SEND  ● 0.35 SOL · 4 tries/slot · exit …"
	lw := 9
	for _, b := range B {
		lw = max(lw, ansi.StringWidth(b.short)+2)
	}
	var out []string
	if !panel {
		out = append(out, m.rule("CONFIG", "", w))
	}
	sep := t.Dim.Render("  ")
	for _, b := range B {
		var lg, sh []string
		for _, l := range b.lines {
			lg, sh = append(lg, l.long), append(sh, l.short)
		}
		txt := strings.Join(lg, sep)
		if ansi.StringWidth(txt) > w-lw {
			txt = strings.Join(sh, sep)
		}
		out = append(out, cut(t.AccB.Render(padRight(b.short, lw)), w)+cut(txt, max(1, w-lw)))
	}
	return out
}

// blockItems: the items of block bi in the block's order (unknown keys last, in their own order).
func blockItems(items []core.CfgItem, bi int) []core.CfgItem {
	var out []core.CfgItem
	for _, k := range cfgBlockKeys[bi] {
		for _, it := range items {
			if it.Key == k {
				out = append(out, it)
			}
		}
	}
	for _, it := range items {
		if blockOf(it.Key) == bi && !known(it.Key) {
			out = append(out, it)
		}
	}
	return out
}

func known(key string) bool {
	for _, ks := range cfgBlockKeys {
		for _, k := range ks {
			if k == key {
				return true
			}
		}
	}
	return false
}
