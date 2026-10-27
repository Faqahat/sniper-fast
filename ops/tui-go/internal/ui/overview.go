package ui

import (
	"fmt"
	"image/color"
	"math"
	"strings"
	"time"

	"charm.land/bubbles/v2/progress"
	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"

	"dipmon/internal/core"
)

// ------------------------------------------------------------------------------------------------- money text

// money is "+0.1234 SOL  +$12.34" (the primary unit first, colored; the other dim).
func (m *Model) money(lam int64, ok bool, d int) string {
	t := m.th
	if !ok {
		return t.Lbl.Render(core.G.Dash)
	}
	st := t.Money(lam, true, false)
	s := core.Sol(lam, true, d, true) + " SOL"
	u := "USD n/a"
	if m.view.Price != 0 {
		u = core.Usd(lam, true, m.view.Price, true, 2)
	}
	if m.usdFirst && m.view.Price != 0 {
		return st.Render(u) + t.Lbl.Render("  "+s)
	}
	return st.Render(s) + t.Lbl.Render("  "+u)
}

// bal is a balance without a sign: "5.5201 SOL  $1,035.20".
func (m *Model) bal(lam int64, ok bool, d int, st lipgloss.Style) string {
	t := m.th
	if !ok {
		return t.Lbl.Render(core.G.Dash)
	}
	s := core.F(float64(lam)/core.LAM, d) + " SOL"
	u := core.UsdAmt(lam, true, m.view.Price, false)
	if m.usdFirst && m.view.Price != 0 {
		return st.Render(u) + t.Lbl.Render("  "+s)
	}
	return st.Render(s) + t.Lbl.Render("  "+u)
}

// ------------------------------------------------------------------------------------------------- gauges

// bar is a gradient progress bar (Bubbles progress, static ViewAs), cached by its filled cells: a gradient bar renders
// every cell with its own style, and it only changes when a cell fills.
func (m *Model) bar(frac float64, w int, stops ...color.Color) string {
	if w < 2 {
		return ""
	}
	frac = math.Max(0, math.Min(1, frac))
	key := fmt.Sprintf("%d|%d|%v|%v|%v", w, int(math.Round(frac*float64(w))), m.ascii, m.th.Mono, stops)
	if s, ok := m.barCache[key]; ok {
		return s
	}
	out := m.barRaw(frac, w, stops...)
	if len(m.barCache) > 256 {
		m.barCache = map[string]string{}
	}
	m.barCache[key] = out
	return out
}

func (m *Model) barRaw(frac float64, w int, stops ...color.Color) string {
	full, empty := '━', '─'
	if m.ascii {
		full, empty = '=', '-'
	}
	opts := []progress.Option{progress.WithWidth(w), progress.WithoutPercentage(), progress.WithFillCharacters(full, empty)}
	if !m.th.Mono {
		if len(stops) == 0 {
			stops = []color.Color{m.th.Violet, m.th.Pink}
		}
		opts = append(opts, progress.WithColors(stops...), progress.WithScaled(true))
	}
	p := progress.New(opts...)
	if m.th.Mono {
		p.FullColor, p.EmptyColor = lipgloss.NoColor{}, lipgloss.NoColor{}
	} else {
		p.EmptyColor = m.th.Border
	}
	return p.ViewAs(frac)
}

// riskBar is a gauge whose color moves green -> yellow -> red as risk grows (frac = risk 0..1).
func (m *Model) riskBar(left float64, w int) string {
	t := m.th
	var stops []color.Color
	switch {
	case left > 0.6:
		stops = []color.Color{t.Green, t.Green}
	case left > 0.3:
		stops = []color.Color{t.Yellow, t.Green}
	default:
		stops = []color.Color{t.Red, t.Yellow}
	}
	return m.bar(left, w, stops...)
}

// usageBar fills with use (0..1): green, then yellow past 60%, red past 85%.
func (m *Model) usageBar(used float64, w int) string {
	t := m.th
	var stops []color.Color
	switch {
	case used > 0.85:
		stops = []color.Color{t.Yellow, t.Red}
	case used > 0.6:
		stops = []color.Color{t.Green, t.Yellow}
	default:
		stops = []color.Color{t.Green, t.Green}
	}
	return m.bar(used, w, stops...)
}

// ------------------------------------------------------------------------------------------------- hero

// heroValue is the displayed run P&L in SOL (the spring's position while it rolls).
func (m *Model) heroValue() float64 {
	if m.anim && m.heroInit {
		return m.heroPos
	}
	return float64(m.view.Total) / core.LAM
}

func (m *Model) heroStyle() lipgloss.Style {
	t := m.th
	v := m.view
	st := t.Money(v.Total, true, true)
	if m.anim && !m.flashAt.IsZero() && m.now().Sub(m.flashAt) < 900*time.Millisecond && !t.Mono {
		c := t.Green
		if m.toastAmt < 0 {
			c = t.Red
		}
		st = lipgloss.NewStyle().Foreground(lipgloss.Lighten(c, 0.25)).Bold(true)
	}
	return st
}

// toast is the small fading "+0.047" next to the hero's title.
func (m *Model) toast() string {
	if !m.anim || m.toastAt.IsZero() {
		return ""
	}
	age := m.now().Sub(m.toastAt)
	if age >= animSpan || m.toastAmt == 0 {
		return ""
	}
	t := m.th
	c := t.Green
	sym := m.g("▲", "^")
	if m.toastAmt < 0 {
		c, sym = t.Red, m.g("▼", "v")
	}
	if !t.Mono {
		k := float64(age) / float64(animSpan)
		c = lipgloss.Blend1D(10, c, t.Faint)[min(9, int(k*10))]
	}
	return lipgloss.NewStyle().Foreground(c).Bold(true).Render(sym + " " + core.Sol(m.toastAmt, true, 4, true))
}

// heroLines: the run P&L in big numerals (u swaps which unit is the giant one), per hour, pre-send vs regular.
func (m *Model) heroLines(cw int, rows int, extra bool) []string {
	t := m.th
	v := m.view
	x := m.heroValue()
	solTxt := core.FS(x, 3)
	if math.Abs(x) >= 1000 {
		solTxt = core.FS(x, 1)
	}
	usdTxt := ""
	if v.Price != 0 {
		u := x * v.Price
		usdTxt = core.FS(u, 2)
		if math.Abs(u) >= 1e6 {
			usdTxt = core.FS(u, 0)
		}
	}
	pt, pu, qt, qu := solTxt, "SOL", usdTxt, "USD"
	if m.usdFirst && usdTxt != "" {
		pt, pu, qt, qu = usdTxt, "USD", solTxt, "SOL"
	}
	st := m.heroStyle()
	var out []string
	P := bigText(pt, rows, m.ascii)
	for i, r := range P {
		l := st.Render(r)
		if i == len(P)-1 {
			l += t.Lbl.Render("  " + pu)
		}
		out = append(out, l)
	}
	if qt != "" {
		Q := bigText(qt, rows, m.ascii) // SOL and USD at equal weight; u swaps which comes first
		qs := st
		if !t.Mono {
			qs = st.Faint(false).Bold(false)
		}
		for i, r := range Q {
			l := qs.Render(r)
			if i == len(Q)-1 {
				l += t.Lbl.Render("  " + qu)
			}
			out = append(out, l)
		}
	} else {
		out = append(out, t.Lbl.Render("USD n/a"))
	}
	if !extra {
		return out
	}
	ph := int64(0)
	if v.HasPerHour {
		ph = int64(v.PerHour)
	}
	out = append(out, m.kv("per hour", 10, m.money(ph, v.HasPerHour, 4)))
	ps, rg := v.PS, v.Reg
	psTxt := t.Lbl.Render("off")
	if ps.Active {
		psTxt = t.Money(ps.Net, true, false).Render(core.SolS(ps.Net))
	}
	split := m.kv("split", 10, t.Lbl.Render("pre-send ")+psTxt+t.Lbl.Render("  regular ")+t.Money(rg.Total, true, false).Render(core.SolS(rg.Total)))
	if ansi.StringWidth(split) > cw {
		split = m.kv("split", 10, t.Lbl.Render("PS ")+psTxt+t.Lbl.Render("  REG ")+t.Money(rg.Total, true, false).Render(core.SolS(rg.Total)))
	}
	out = append(out, split)
	return out
}

// ------------------------------------------------------------------------------------------------- run / wallet

func (m *Model) runLines(cw int) []string {
	t := m.th
	v := m.view
	var out []string
	dot := t.StateDot(StatusState(v.Status), m.ascii)
	l1 := dot + " " + t.StatusStyle(v.Status).Render(v.Status)
	if v.HowEnded != "" {
		l1 += t.Lbl.Render("  " + v.HowEnded)
	}
	if v.NSess > 1 {
		if v.Scope < 0 {
			l1 += t.Lbl.Render(fmt.Sprintf("  %d sessions", v.NSess))
		} else {
			l1 += t.Lbl.Render(fmt.Sprintf("  session %d/%d", v.Scope+1, v.NSess))
		}
	}
	out = append(out, l1)
	t0 := v.TFirst
	if v.Scope >= 0 {
		t0 = v.ST0
	}
	endTxt := "?"
	endLbl := "planned"
	if v.Status == "ENDED" && v.TEnd != 0 {
		endTxt, endLbl = core.T12(float64(v.TEnd), false), "ended"
	} else if v.HasEndsAt {
		endTxt = core.T12(v.EndsAt, false)
	}
	out = append(out, t.Val.Render(core.T12(float64(t0), false))+t.Lbl.Render(" "+m.g("→", "->")+" ")+t.Val.Render(endTxt)+t.Lbl.Render(" PKT  ("+endLbl+")"))
	el := v.Elapsed
	elok := v.HasElapsed
	if v.Planned.Truthy() {
		el, elok = v.SElapsed, v.HasSElapsed
	}
	l3 := t.Lbl.Render(m.g("◷ ", "")) + t.Val.Render(core.Dur(el, elok))
	if v.Planned.Truthy() {
		l3 += t.Lbl.Render(" / " + core.Dur(v.Planned.Float()*60, true))
		frac := v.SElapsed / (v.Planned.Float() * 60)
		pct := t.Lbl.Render(fmt.Sprintf(" %3.0f%%", math.Min(frac, 9.99)*100))
		gw := cw - ansi.StringWidth(l3) - ansi.StringWidth(pct) - 2
		if gw >= 6 {
			l3 += "  " + m.bar(frac, gw) + pct
		} else {
			out = append(out, l3)
			l3 = m.bar(frac, max(6, cw-6)) + pct
		}
	}
	out = append(out, l3)
	return out
}

func (m *Model) walletLines(cw int) []string {
	t := m.th
	v := m.view
	var out []string
	if !v.HasEstNow {
		return []string{t.Lbl.Render("START BALANCE not in the log yet")}
	}
	out = append(out, m.kv("now est.", 10, m.bal(v.EstNow, true, 4, t.B)))
	out = append(out, m.kv("start", 10, m.bal(v.StartBal, true, 4, t.Val)))
	if v.HasKillLevel {
		bad := float64(v.KillDist) < 0.15*core.LAM
		ks := t.Val
		if bad {
			ks = t.Bad
		}
		line := m.kv("kill sw.", 10, ks.Render(core.F(float64(v.KillLevel)/core.LAM, 4))+t.Lbl.Render("  ")+
			ks.Render(core.F(float64(v.KillDist)/core.LAM, 3))+t.Lbl.Render(" away"))
		if v.HasLossUsed {
			gw := cw - ansi.StringWidth(line) - 2
			if gw >= 6 {
				line += "  " + m.riskBar(1-v.LossUsed, min(gw, 24))
			}
		}
		out = append(out, line)
	}
	if v.HasBudget {
		b := m.kv("budget", 10, t.Val.Render(core.F(float64(v.BudgetLeft)/core.LAM, 3)+" SOL")+
			t.Lbl.Render(" left of "+core.F(float64(v.BudgetMax)/core.LAM, 2)+"  "+core.UsdAmt(v.BudgetLeft, true, v.Price, false)))
		if ansi.StringWidth(b) > cw {
			b = m.kv("budget", 10, t.Val.Render(core.F(float64(v.BudgetLeft)/core.LAM, 3))+t.Lbl.Render(" left of "+core.F(float64(v.BudgetMax)/core.LAM, 2)))
		}
		out = append(out, b)
	}
	return out
}

// ------------------------------------------------------------------------------------------------- the card

func (m *Model) card() core.Card {
	if m.todayOn {
		return m.todayCard
	}
	v := m.view
	sel := v.Sessions
	if v.Scope >= 0 {
		sel = []*core.Sess{v.S}
	}
	return core.CardOf(sel, nil)
}

func (m *Model) cardTitle() (string, string) {
	v := m.view
	t := m.th
	if m.todayOn {
		c := m.todayCard
		runs := make([]string, len(c.Runs))
		for i, r := range c.Runs {
			runs[i] = fmt.Sprint(r)
		}
		r := "runs " + strings.Join(runs, ", ")
		if c.Loading > 0 {
			r += fmt.Sprintf(" (+%d loading)", c.Loading)
		}
		return "TODAY " + m.g("·", "|") + " " + c.Label, t.Lbl.Render(r)
	}
	ttl := "THIS RUN"
	if v.HasRun {
		ttl += " " + m.g("·", "|") + " " + v.Region + " r" + fmt.Sprint(v.Run)
	}
	return ttl, t.Lbl.Render("s: today")
}

// athLines: the scope's ATH (the highest P&L of the series the chart draws: the run's, or the day's with s) in green,
// its low in red, and the drawdown from the ATH now; SOL and USD (u swaps them) and the minute in 12-hour PKT, each in
// the longest form that fits cw cells. ok is false while the series has not moved.
func (m *Model) athLines(lw int, suffix string, cw int) (ath, low, from, fromShort string, ok bool) {
	s := m.pnl()
	if !s.Ok() {
		return
	}
	a, at := s.ATH()
	l, lt := s.Low()
	if a == 0 && l == 0 {
		return
	}
	t := m.th
	pr := m.view.Price
	// forms: 0 "+0.606 SOL  $113.51", 1 "+0.606 SOL $113.51", 2 "+0.606 $113.51", 3 "+0.606 SOL"
	val := func(x int64, form int) string {
		so := core.SolAuto(x)
		if form != 2 {
			so += " SOL"
		}
		if pr == 0 || form == 3 {
			return t.Money(x, true, true).Render(so)
		}
		gap := "  "
		if form > 0 {
			gap = " "
		}
		us := core.Usd(x, true, pr, x < 0, 2)
		if m.usdFirst {
			return t.Money(x, true, true).Render(us) + gap + t.Money(x, true, false).Render(so)
		}
		return t.Money(x, true, true).Render(so) + gap + t.Money(x, true, false).Render(us)
	}
	// one form for both lines (the first where both fit), so they stay aligned
	line := func(label string, x int64, tns float64, form int, tight bool) string {
		sep := t.Lbl.Render(" " + m.g("·", "|") + " ")
		if form > 0 {
			sep = t.Lbl.Render(" ")
		}
		if tight {
			return t.Lbl.Render(label+" ") + val(x, form) + sep + t.Lbl.Render(core.T12(tns, false))
		}
		return m.kv(label, lw, val(x, form)+sep+t.Lbl.Render(core.T12(tns, false)))
	}
	found := false
	for form := 0; form < 4 && !found; form++ {
		for _, tight := range []bool{false, true} {
			ath, low = line("ATH"+suffix, a, at, form, tight), line("Low"+suffix, l, lt, form, tight)
			if ansi.StringWidth(ath) <= cw && ansi.StringWidth(low) <= cw {
				found = true
				break
			}
		}
	}
	ath, low = cut(ath, cw), cut(low, cw)
	f := s.FromATH()
	if f == 0 {
		from = m.kv("from ATH", lw, t.Pos.Render("at the ATH"))
		fromShort = t.Pos.Render("at the ATH")
	} else {
		from = m.kv("from ATH", lw, val(f, 0))
		if ansi.StringWidth(from) > cw {
			from = m.kv("from ATH", lw, val(f, 3))
		}
		fromShort = t.Lbl.Render("from ATH ") + t.Money(f, true, false).Render(core.SolAuto(f))
	}
	return ath, low, cut(from, cw), fromShort, true
}

// cardLines: the card (rows > 0: at most that many lines when it can be done by merging the txns and the volume,
// then by putting "from ATH" beside the ATH).
func (m *Model) cardLines(cw int, compact bool, rows int) []string {
	t := m.th
	c := m.card()
	pr := m.view.Price
	pm := func(lam int64, st lipgloss.Style, neg bool) string {
		s := core.F(float64(lam)/core.LAM, 4)
		if neg && lam != 0 {
			s = "-" + s
		} else if !neg && lam != 0 {
			s = "+" + s
		}
		u := "$" + core.FC(float64(lam)/core.LAM*pr, 2)
		if pr == 0 {
			u = "USD n/a"
		}
		if m.usdFirst && pr != 0 {
			return st.Render(u) + t.Lbl.Render("  "+s+" SOL")
		}
		return st.Render(s+" SOL") + t.Lbl.Render("  "+u)
	}
	var out []string
	if compact {
		out = append(out, t.Lbl.Render("profit ")+pm(c.Profit, t.PosB, false)+t.Lbl.Render("   loss ")+pm(c.Loss, t.NegB, true))
	} else {
		out = append(out, m.kv("Profit", 9, pm(c.Profit, t.PosB, false)))
		out = append(out, m.kv("Loss", 9, pm(c.Loss, t.NegB, true)))
	}
	txns := t.Lbl.Render("buy ") + t.Pos.Render(fmt.Sprint(c.Buys)) + t.Lbl.Render(" / sell ") + t.Neg.Render(fmt.Sprint(c.Sells))
	out = append(out, m.kv("Txns", 9, txns))
	txnsAt := len(out) - 1
	volS := t.Pos.Render(core.FC(float64(c.BuySol)/core.LAM, 1)) + t.Lbl.Render(" / ") + t.Neg.Render(core.FC(float64(c.SellSol)/core.LAM, 1))
	vol := volS + t.Lbl.Render(" SOL")
	if pr != 0 {
		vu := t.Lbl.Render(" "+m.g("·", "|")+" ") + t.Pos.Render(core.UsdAmt(c.BuySol, true, pr, true)) + t.Lbl.Render(" / ") + t.Neg.Render(core.UsdAmt(c.SellSol, true, pr, true))
		if ansi.StringWidth(vol+vu)+9 <= cw {
			vol += vu
		}
	}
	volAt := -1
	if !compact {
		out = append(out, m.kv("Volume", 9, vol))
		volAt = len(out) - 1
		dot := t.Dim.Render("  " + m.g("·", "|") + "  ")
		if cw < 44 {
			dot = t.Dim.Render(" " + m.g("·", "|") + " ")
		}
		var x []string
		if wr, ok := c.WinRate(); ok {
			x = append(x, t.Lbl.Render("win ")+t.Val.Render(core.F(wr*100, 0)+"%"))
		}
		aw, okw := c.AvgWin()
		al, okl := c.AvgLoss()
		avg := ""
		if okw || okl {
			a, b := core.G.Dash, core.G.Dash
			if okw {
				a = core.Sol(aw, true, 4, true)
			}
			if okl {
				b = core.Sol(-al, true, 4, true)
			}
			avg = t.Lbl.Render("avg ") + t.Pos.Render(a) + t.Lbl.Render(" / ") + t.Neg.Render(b)
		}
		pf := ""
		if p, ok := c.PF(); ok {
			pf = t.Lbl.Render("PF ") + t.Val.Render(core.F(p, 2))
		}
		one := strings.Join(nonEmpty(append(x, avg, pf)...), dot)
		if ansi.StringWidth(one) <= cw {
			out = append(out, one)
		} else {
			out = append(out, strings.Join(nonEmpty(append(x, pf)...), dot))
			if avg != "" {
				out = append(out, avg)
			}
		}
	}
	net := t.Lbl.Render("fees "+core.Sol(-c.Fees, true, 3, true)+" "+m.g("·", "|")+" rent "+core.Sol(c.Rent, true, 3, true)+" "+m.g("→", "->")+" net ") +
		t.Money(c.Net, true, true).Render(core.SolS(c.Net))
	if ansi.StringWidth(net) > cw {
		net = t.Lbl.Render("fees "+core.Sol(-c.Fees, true, 3, true)+" rent "+core.Sol(c.Rent, true, 3, true)+" "+m.g("→", "->")+" ") +
			t.Money(c.Net, true, true).Render(core.SolS(c.Net))
	}
	out = append(out, net)
	if compact {
		return out
	}
	ath, low, from, fromShort, ok := m.athLines(9, "", cw)
	if !ok {
		return out
	}
	out = append(out, ath, low, from)
	if rows <= 0 || len(out) <= rows {
		return out
	}
	// merge the txns and the volume (SOL only)
	sepT := t.Lbl.Render(" " + m.g("·", "|") + " ")
	bs := t.Pos.Render(fmt.Sprint(c.Buys)) + t.Lbl.Render(" / ") + t.Neg.Render(fmt.Sprint(c.Sells))
	for _, mv := range []string{txns + sepT + vol, txns + sepT + volS + t.Lbl.Render(" SOL"), txns + sepT + t.Lbl.Render("vol ") + volS,
		bs + sepT + t.Lbl.Render("vol ") + volS} {
		if x := m.kv("Txns", 9, mv); ansi.StringWidth(x) <= cw && volAt > txnsAt {
			out[txnsAt] = x
			out = append(out[:volAt], out[volAt+1:]...)
			break
		}
	}
	if len(out) <= rows {
		return out
	}
	// "from ATH" beside the ATH, or left out (the chart's title shows it too)
	out = out[:len(out)-1]
	if x := ath + "  " + fromShort; ansi.StringWidth(x) <= cw {
		out[len(out)-2] = x
	}
	return out
}

func nonEmpty(xs ...string) []string {
	var out []string
	for _, x := range xs {
		if x != "" {
			out = append(out, x)
		}
	}
	return out
}

// gridWidth is the natural width of gridLines' layout.
func gridWidth(cells []string, rows int, sep string) int {
	if len(cells) == 0 {
		return 0
	}
	cols := (len(cells) + rows - 1) / rows
	w := ansi.StringWidth(sep) * (cols - 1)
	for k := 0; k < cols; k++ {
		cw := 0
		for r := 0; r < rows; r++ {
			if i := k*rows + r; i < len(cells) {
				cw = max(cw, ansi.StringWidth(cells[i]))
			}
		}
		w += cw
	}
	return w
}

// cfgStrip packs the config badges (the snapshot's short forms) into at most maxLines lines.
func (m *Model) cfgStrip(w, maxLines int) []string {
	t := m.th
	v := m.view
	var out []string
	cur := ""
	for _, it := range v.CfgItems {
		switch it.Key {
		case "kill", "planned", "skipcl":
			continue
		}
		seg := ""
		if it.State != "na" {
			seg = t.StateDot(it.State, m.ascii) + " "
		}
		st := t.Val
		if it.State == "na" {
			st = t.Lbl
		}
		seg += st.Render(it.Short)
		if cur != "" && ansi.StringWidth(cur)+2+ansi.StringWidth(seg) > w {
			out = append(out, cur)
			cur = ""
			if len(out) >= maxLines {
				return out
			}
		}
		if cur != "" {
			cur += "  "
		}
		cur += seg
	}
	if cur != "" && len(out) < maxLines {
		out = append(out, cur)
	}
	return out
}

// gridLines lays short cells into rows of aligned columns (the LIVE strip).
func gridLines(cells []string, w, rows int, sep string) []string {
	if len(cells) == 0 {
		return nil
	}
	cols := (len(cells) + rows - 1) / rows
	widths := make([]int, cols)
	for i, c := range cells {
		k := i / rows
		widths[k] = max(widths[k], ansi.StringWidth(c))
	}
	sw := ansi.StringWidth(sep)
	out := make([]string, rows)
	for r := 0; r < rows; r++ {
		var b strings.Builder
		for k := 0; k < cols; k++ {
			i := k*rows + r
			if i >= len(cells) {
				break
			}
			if k > 0 {
				b.WriteString(sep)
			}
			if k < cols-1 {
				b.WriteString(fitLine(cells[i], widths[k]))
			} else {
				b.WriteString(cells[i])
			}
		}
		out[r] = cut(b.String(), w)
		_ = sw
	}
	return out
}

// ------------------------------------------------------------------------------------------------- live

// liveCompact is LIVE in one line for the medium layout: the pre-send fills and the windows (the tries only when they
// fit), else the regular buys.
func (m *Model) liveCompact(w int) string {
	t := m.th
	v := m.view
	ps, g := v.PS, v.Reg
	sep := t.Dim.Render(" " + m.g("·", "|") + " ")
	if !ps.Active {
		nf := g.Guard + g.Lighthouse + g.Failed
		return cut(t.Lbl.Render("regular ")+t.Val.Render(fmt.Sprintf("%d buys", g.Fires))+t.Lbl.Render(" "+m.g("→", "->")+" ")+
			t.Val.Render(fmt.Sprintf("%d fills", g.Fills))+sep+t.Val.Render(fmt.Sprintf("%d failed", nf))+sep+t.Val.Render(fmt.Sprintf("%d W", g.Wins)), w)
	}
	l := t.Lbl.Render("pre-send ") + t.Val.Render(fmt.Sprintf("%d fills", ps.Fills)) + sep + t.Val.Render(fmt.Sprintf("%d W", ps.Wins))
	if ps.NReal > 0 {
		l += t.Lbl.Render(fmt.Sprintf(" %.0f%%", float64(ps.Wins)/float64(ps.NReal)*100))
	}
	if ps.Fills > 0 {
		avg := int64(float64(ps.Real) / float64(ps.Fills))
		l += sep + t.Lbl.Render("avg ") + t.Money(avg, true, false).Render(core.SolS(avg))
	}
	arm := t.Val.Render(fmt.Sprint(v.PSOpenNow))
	if v.PSOpenNow > 0 && v.Running {
		frames := []string{"⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"}
		sp := frames[m.armFrame%len(frames)]
		if m.ascii {
			sp = []string{"|", "/", "-", "\\"}[m.armFrame%4]
		}
		arm = t.Acc.Render(sp) + " " + t.B.Render(fmt.Sprint(v.PSOpenNow))
	}
	win := t.Dim.Render("   ") + t.Lbl.Render("windows ") + arm + t.Lbl.Render(" now") + sep + t.Lbl.Render(core.IC(ps.Armed)+" armed")
	tries := sep + t.Lbl.Render(core.IC(ps.Sent)+" tries")
	for _, c := range []string{l + win + tries, l + win} {
		if ansi.StringWidth(c) <= w {
			return c
		}
	}
	return cut(l, w)
}

func (m *Model) liveLines(cw int, compact bool) []string {
	t := m.th
	v := m.view
	ps, g := v.PS, v.Reg
	sep := t.Dim.Render(" " + m.g("·", "|") + " ")
	var out []string
	if ps.Active {
		l := t.Val.Render(fmt.Sprintf("%d fills", ps.Fills)) + sep + t.Val.Render(fmt.Sprintf("%d W", ps.Wins))
		if ps.NReal > 0 {
			l += t.Lbl.Render(fmt.Sprintf(" %.0f%%", float64(ps.Wins)/float64(ps.NReal)*100))
		}
		if ps.Fills > 0 {
			avg := int64(float64(ps.Real) / float64(ps.Fills))
			l += sep + t.Lbl.Render("avg ") + t.Money(avg, true, false).Render(core.SolS(avg))
		}
		out = append(out, m.kv("pre-send", 10, l))
		frames := []string{"⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"}
		arm := t.Val.Render(fmt.Sprint(v.PSOpenNow))
		if v.PSOpenNow > 0 && v.Running {
			sp := frames[m.armFrame%len(frames)]
			if m.ascii {
				sp = []string{"|", "/", "-", "\\"}[m.armFrame%4]
			}
			arm = t.Acc.Render(sp) + " " + t.B.Render(fmt.Sprint(v.PSOpenNow))
		}
		out = append(out, m.kv("windows", 10, arm+t.Lbl.Render(" now")+sep+t.Lbl.Render(core.IC(ps.Armed)+" armed")+sep+t.Lbl.Render(core.IC(ps.Sent)+" tries")))
		if v.Quiet.Present {
			q := v.Quiet
			state := q.State
			stDot := map[string]string{"on": "on", "warm-up": "part"}[state]
			if stDot == "" {
				stDot = "off"
			}
			pre := m.kv("QUIET", 10, t.Val.Render(fmt.Sprintf("%d skips", ps.QSkips))+sep+t.Val.Render(fmt.Sprintf("%d stops", ps.QStops))+sep)
			rule := t.StateDot(stDot, m.ascii) + " " + t.Val.Render(state)
			if state == "warm-up" && q.HasOnAt {
				left := float64(q.OnAt)/1e9 - m.nowSec()
				rule = t.StateDot("part", m.ascii) + " " + t.Warn.Render("warm-up")
				if left > 0 { // the skip rule turns on at ... (in ...), or just the countdown when the panel is narrow
					for _, c := range []string{rule + t.Lbl.Render(" on "+core.T12(float64(q.OnAt), false)+" ("+core.Dur(left, true)+")"),
						rule + t.Lbl.Render(" "+core.Dur(left, true))} {
						if ansi.StringWidth(pre+c) <= cw {
							rule = c
							break
						}
					}
				}
			}
			out = append(out, pre+rule)
		}
	}
	nf := g.Guard + g.Lighthouse + g.Failed
	out = append(out, m.kv("regular", 10, t.Val.Render(fmt.Sprintf("%d buys", g.Fires))+t.Lbl.Render(" "+m.g("→", "->")+" ")+
		t.Val.Render(fmt.Sprintf("%d fills", g.Fills))+sep+t.Val.Render(fmt.Sprintf("%d failed", nf))+sep+t.Val.Render(fmt.Sprintf("%d W", g.Wins))))
	if compact {
		return out
	}
	// landing: how long after the dump the fills / the regular buys landed (medians); the fills' send -> seen when the
	// records have no dump -> land
	rm, okr := core.Med(g.LandMs)
	psL := ""
	if fq, ok := m.latSummary().All.FillDL.Quantile(0.5); ok {
		psL = t.Lbl.Render("PS ") + m.latStyle(fq).Render(latMs(core.FloatNum(fq))+" ms")
	} else if lm, okl := core.Med(ps.LandMs); okl {
		psL = t.Lbl.Render("PS send→seen ") + t.Val.Render(core.F(lm, 0)+" ms")
	}
	if psL != "" || okr {
		l := psL
		if okr {
			if l != "" {
				l += sep
			}
			l += t.Lbl.Render("REG ") + m.latStyle(rm).Render(core.F(rm, 0)+" ms")
		}
		out = append(out, m.kv("landing", 10, l+t.Lbl.Render(" after the dump")))
	}
	if ps.Paper {
		out = append(out, m.kv("paper", 10, t.Val.Render(fmt.Sprintf("%d fills", ps.PaperFills))+t.Lbl.Render(" net ")+
			t.Money(int64(ps.PaperNet*core.LAM), true, false).Render(core.FS(ps.PaperNet, 3))+t.Lbl.Render("  vs live ")+
			t.Money(ps.Net, true, false).Render(core.Sol(ps.Net, true, 3, true))))
	}
	if g.OpenList != nil && len(g.OpenList) > 0 {
		tr := g.OpenList[len(g.OpenList)-1]
		state := "in flight"
		if tr.Res == "filled" {
			state = "holding"
		}
		out = append(out, m.kv("open", 10, t.Val.Render(core.Short(tr.Mint, 8)+" "+core.F(float64(tr.Spend.Int())/core.LAM, 2)+" SOL")+t.Warn.Render("  "+state)))
	}
	return out
}

func (m *Model) nowSec() float64 {
	if m.ctx.FixedNow != 0 {
		return m.ctx.FixedNow
	}
	return float64(m.now().UnixNano()) / 1e9
}

// ------------------------------------------------------------------------------------------------- config cells

// cfgCell is one labeled config item in its long and short forms.
type cfgCell struct{ long, short string }

// cfgCells are the overview's config items, in reading order: Pre-send, Fills, QUIET, Regular, Paper / M2 / Dev,
// Routes / fan-outs / gates, Kill switch / planned / engine.
func (m *Model) cfgCells() []cfgCell {
	return []cfgCell{
		{m.cfgCell(0, false), m.cfgCell(0, true)}, {m.cfgCell(1, false), m.cfgCell(1, true)},
		{m.cfgCell(2, false), m.cfgCell(2, true)}, {m.cfgCell(3, false), m.cfgCell(3, true)},
		{m.cfgCell(4, false), m.cfgCell(4, true)}, {m.cfgCell(5, false), m.cfgCell(5, true)},
		{m.cfgCell(6, false), m.cfgCell(6, true)},
	}
}

func (m *Model) cfgCell(i int, short bool) string {
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
	tpsl := func(tp float64, tpOK bool, sl float64, slots string) string {
		tps := "off"
		if tpOK {
			tps = "+" + core.F(tp, 0) + "%"
		}
		if short {
			return "TP " + tps + " SL " + minus + core.F(sl, 0) + "% " + slots + "sl"
		}
		return "TP " + tps + " / SL " + minus + core.F(sl, 0) + "% / " + slots + " slots"
	}
	switch i {
	case 0, 1:
		ps := it("ps")
		if ps == nil || ps.State == "off" {
			if i == 1 {
				return ""
			}
			return t.Lbl.Render("Pre-send ") + dot("off") + t.Lbl.Render(" off")
		}
		if i == 0 {
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
			txt := t.Val.Render(" "+spend+" SOL") + sep + t.Val.Render(k+" tries/slot") + sep + t.Val.Render("exit "+tpsl(tp, tpOK && tpN.Truthy(), sl, slots))
			if short {
				txt = t.Val.Render(" "+spend) + sep + t.Val.Render(k+"/slot") + sep + t.Val.Render(tpsl(tp, tpOK && tpN.Truthy(), sl, slots))
			}
			c := t.Lbl.Render("Pre-send ") + dot(ps.State) + txt
			if v.PSStopped != "" {
				c += t.Warn.Render(" · stopped: " + v.PSStopped)
			}
			return c
		}
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
		return t.Lbl.Render("Fills ") + t.Val.Render(fmt.Sprintf("%d/%s", sf, capS)) + sep + t.Lbl.Render("fees ") + fs.Render(core.F(float64(sfee)/core.LAM, 2)+"/"+core.F(bud/core.LAM, 2))
	case 2:
		q := v.Quiet
		if !q.Present {
			x := " off"
			if !short {
				x += " (not in this engine)"
			}
			return t.Lbl.Render("QUIET ") + dot("off") + t.Lbl.Render(x)
		}
		stopOn := q.HasStop && q.Stop != "" && q.Stop != "off"
		n, mm := "?", "?"
		if stopOn && strings.Contains(q.Stop, ":") {
			p := strings.SplitN(q.Stop, ":", 2)
			n, mm = p[0], p[1]
		}
		skip := map[string]string{"on": "on", "warm-up": "part"}[q.State]
		if skip == "" {
			skip = "off"
		}
		st := "off"
		if stopOn {
			st = "on"
		}
		c := t.Lbl.Render("QUIET ") + dot(st)
		if short || !stopOn {
			c += t.Val.Render(" stop  ")
		} else {
			c += t.Val.Render(" stop (" + n + " slots, < " + mm + " trades)  ")
		}
		c += dot(skip) + t.Val.Render(" skip")
		if q.State == "warm-up" && q.HasOnAt {
			c += t.Warn.Render(" on " + core.T12(float64(q.OnAt), false))
		}
		return c
	case 3:
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
		rc := t.Lbl.Render("Regular ")
		if rstate != "na" {
			rc += dot(rstate) + " "
		}
		sp := "?"
		if spend.Ok() {
			sp = core.F(spend.Float()/core.LAM, 2)
		}
		if short {
			rc += t.Val.Render(sp) + sep + t.Val.Render(tpsl(tp, tpOK, sl, hold))
			if guard > 0 {
				rc += sep + t.Val.Render("+"+core.F((guard-1)*100, 0)+"%")
			}
			return rc
		}
		rc += t.Val.Render(sp+" SOL") + sep + t.Val.Render("exit "+tpsl(tp, tpOK, sl, hold))
		if guard > 0 {
			rc += sep + t.Val.Render("guard +"+core.F((guard-1)*100, 0)+"%")
		}
		return rc
	case 4:
		var seg []string
		for _, kl := range [][2]string{{"paper", "Paper"}, {"m2", "M2 gate"}, {"dev", "Dev list"}} {
			x := it(kl[0])
			if x == nil {
				continue
			}
			lab := kl[1]
			if short {
				lab = strings.Fields(lab)[0]
			}
			s := t.Lbl.Render(lab+" ") + dot(x.State)
			if kl[0] == "dev" && x.State == "on" {
				s += t.Val.Render(" " + strings.TrimPrefix(x.Short, "dev "))
			}
			if kl[0] == "m2" && x.State != "off" && !short && x.Short != "M2 gate" {
				s += t.Val.Render(" " + strings.TrimPrefix(x.Short, "M2 "))
			}
			seg = append(seg, s)
		}
		return strings.Join(seg, "   ")
	case 5:
		rs := t.Lbl.Render("Routes ")
		if x := it("routes"); x != nil {
			rs += t.Val.Render(x.Short)
		}
		if x := it("sellfan"); x != nil {
			lab := "sell fan-out "
			if short {
				lab = "fan "
			}
			rs += sep + t.Lbl.Render(lab) + dot(x.State)
		}
		if x := it("nonce"); x != nil {
			rs += sep + t.Lbl.Render("nonce ") + dot(x.State)
			if x.State == "on" {
				rs += t.Val.Render(" " + strings.TrimPrefix(x.Short, "nonce "))
			}
		}
		if x := it("near"); x != nil && x.State == "on" {
			lab := "near leaders "
			if short {
				lab = "near "
			}
			rs += sep + t.Lbl.Render(lab) + t.Val.Render(strings.TrimPrefix(x.Short, "near "))
		}
		if x := it("skipcl"); x != nil {
			rs += sep + t.Lbl.Render("skip ") + t.Val.Render(strings.ReplaceAll(x.Full, "rakurai", "Rakurai"))
		}
		return rs
	}
	ks := ""
	if v.HasKillLevel {
		lab := "Kill switch "
		if short {
			lab = "Kill "
		}
		ks += t.Lbl.Render(lab) + t.Val.Render(core.F(float64(v.KillLevel)/core.LAM, 3))
	}
	if v.Planned.Truthy() {
		if ks != "" {
			ks += sep + t.Lbl.Render("planned ")
		} else {
			ks += t.Lbl.Render("Planned ")
		}
		ks += t.Val.Render(core.HMS(v.Planned.Float()*60, true, false))
	}
	if ks != "" {
		ks += sep + t.Lbl.Render("engine ")
	} else {
		ks += t.Lbl.Render("Engine ")
	}
	return ks + t.Val.Render(v.Build)
}

// configCols: how many columns configGrid uses at w with maxRows.
func (m *Model) configCols(w, maxRows int) int {
	m.configGrid(w, maxRows)
	return m.cfgCols
}

// configGrid lays the cells out in 3, 2 or 1 columns: the most columns that fit within maxRows, each cell in its
// long form when it fits its column, else the short one (cached until the items, the size or the theme change).
func (m *Model) configGrid(w int, maxRows int) []string {
	var kb strings.Builder
	fmt.Fprintf(&kb, "%d|%d|%v|%v|%s|", w, maxRows, m.dark, m.ascii, m.view.Status)
	for _, it := range m.view.CfgItems {
		kb.WriteString(it.State + it.Short + "|")
	}
	if m.view.Quiet.HasOnAt {
		fmt.Fprintf(&kb, "%d", m.view.Quiet.OnAt)
	}
	key := kb.String()
	if c, ok := m.cfgCache[key]; ok {
		m.cfgCols = c.cols
		return c.lines
	}
	out := m.configGridRaw(w, maxRows)
	if len(m.cfgCache) > 16 {
		m.cfgCache = map[string]cfgCached{}
	}
	m.cfgCache[key] = cfgCached{out, m.cfgCols}
	return out
}

type cfgCached struct {
	lines []string
	cols  int
}

func (m *Model) configGridRaw(w int, maxRows int) []string {
	m.cfgCols = 0
	cells := m.cfgCells()
	orders := map[int][][]int{3: {{0, 1, 2}, {3, 4}, {5, 6}}, 2: {{0, 1, 2, 6}, {3, 4, 5}}, 1: {{0, 1, 2, 3, 4, 5, 6}}}
	gap := 3
	for _, nc := range []int{3, 2, 1} {
		groups := orders[nc]
		rows := 0
		for _, g := range groups {
			rows = max(rows, len(g))
		}
		if rows > maxRows && nc > 1 {
			continue
		}
		// each column at its short or its long width: the subset that fits with the most cells in long form
		shortW := make([]int, nc)
		longW := make([]int, nc)
		gain := make([]int, nc)
		for k, g := range groups {
			for _, i := range g {
				shortW[k] = max(shortW[k], ansi.StringWidth(cells[i].short))
				longW[k] = max(longW[k], ansi.StringWidth(cells[i].long))
				if cells[i].long != cells[i].short {
					gain[k]++
				}
			}
		}
		best, bestScore := -1, -1
		for mask := 0; mask < 1<<nc; mask++ {
			total, score := gap*(nc-1), 0
			for k := 0; k < nc; k++ {
				if mask&(1<<k) != 0 {
					total += longW[k]
					score += gain[k]
				} else {
					total += shortW[k]
				}
			}
			if total <= w && score > bestScore {
				best, bestScore = mask, score
			}
		}
		if best < 0 && nc > 1 {
			continue
		}
		widths := make([]int, nc)
		total := gap * (nc - 1)
		for k := 0; k < nc; k++ {
			widths[k] = shortW[k]
			if best >= 0 && best&(1<<k) != 0 {
				widths[k] = longW[k]
			}
			total += widths[k]
		}
		if spare := w - total; nc > 1 && spare > 0 {
			for k := 0; k < nc-1; k++ {
				widths[k] += spare / nc
			}
		}
		m.cfgCols = nc
		var out []string
		for r := 0; r < rows && r < maxRows; r++ {
			var l strings.Builder
			for k, g := range groups {
				c := ""
				if r < len(g) {
					c = cells[g[r]].long
					if ansi.StringWidth(c) > widths[k] {
						c = cells[g[r]].short
					}
				}
				if k < nc-1 {
					l.WriteString(fitLine(c, widths[k]) + strings.Repeat(" ", gap))
				} else {
					l.WriteString(cut(c, max(1, w-ansi.StringWidth(l.String()))))
				}
			}
			out = append(out, l.String())
		}
		return out
	}
	return nil
}

// ------------------------------------------------------------------------------------------------- overview

func (m *Model) scrOverview(w, bh int) string {
	if w < 70 {
		return m.overviewNarrow(w, bh)
	}
	if w < 120 {
		return m.overviewMedium(w, bh)
	}
	return m.overviewWide(w, bh)
}

// overviewWide: the hero, RUN + WALLET, the card and LIVE side by side; the config; the chart; the last trades.
func (m *Model) overviewWide(w, bh int) string {
	t := m.th
	ncols := 4
	if w < 180 {
		ncols = 3
	}
	gap := 1
	cw := (w - gap*(ncols-1)) / ncols
	lastW := w - (cw+gap)*(ncols-1)
	inner := cw - 4
	big := 3
	hero := m.heroLines(inner, big, false)
	run := m.runLines(inner)
	run = append(run, m.subRule("WALLET", inner))
	run = append(run, m.walletLines(inner)...)
	live := m.liveLines(inner, false)
	base := max(len(run), len(hero)+2)
	if ncols == 4 {
		base = max(base, len(live))
	}
	if bh >= 40 {
		base = max(base, 9) // tall terminals: room for the whole card (txns and volume on their own lines)
	}
	card := m.cardLines(inner, false, base)
	topH := max(base, len(card))
	// the hero: numerals at the top, per hour / split at the bottom
	extra := m.heroLines(inner, big, true)[len(hero):]
	for len(hero)+len(extra) < topH {
		hero = append(hero, "")
	}
	hero = append(hero, extra...)
	ph := topH + 2
	heroTitle := "RUN P&L"
	if m.view.Scope >= 0 {
		heroTitle += fmt.Sprintf(" · session %d", m.view.Scope+1)
	}
	ct, cr := m.cardTitle()
	// the P&L, then its card (profit / loss, the ATH and the low), then the run and the wallet, then LIVE
	panels := []string{
		m.panel(heroTitle, m.toast(), strings.Join(hero, "\n"), cw, ph),
		m.panel(ct, cr, strings.Join(card, "\n"), cw, ph),
	}
	if ncols == 4 {
		panels = append(panels, m.panel("RUN", "", strings.Join(run, "\n"), cw, ph), m.panel("LIVE", "", strings.Join(live, "\n"), lastW, ph))
	} else {
		panels = append(panels, m.panel("RUN", "", strings.Join(run, "\n"), lastW, ph))
	}
	out := []string{hcat(gap, panels...)}
	used := ph
	if ncols == 3 {
		sepS := t.Dim.Render("  " + m.g("│", "|") + "  ")
		ll := m.liveLines(w-4, false)
		if gridWidth(ll, 2, sepS) > w-4 {
			ll = m.liveLines(w-4, true)
		}
		strip := gridLines(ll, w-4, 2, sepS)
		out = append(out, m.panel("LIVE", "", strings.Join(strip, "\n"), w, len(strip)+2))
		used += len(strip) + 2
	}
	rest := bh - used
	// the config: a panel when there is room, else under a rule
	if rest >= 24 {
		cfg := m.configGrid(w-4, 3)
		if len(cfg) == 3 && m.configCols(w-4, 3) == 1 {
			cfg = m.configGrid(w-4, 4)
		}
		out = append(out, m.panel("CONFIG", "", strings.Join(cfg, "\n"), w, len(cfg)+2))
		used += len(cfg) + 2
	} else {
		cfg := m.configGrid(w-2, 3)
		if m.configCols(w-2, 3) == 1 {
			cfg = m.configGrid(w-2, 4)
		}
		out = append(out, m.rule("CONFIG", "", w))
		for _, c := range cfg {
			out = append(out, " "+c)
		}
		used += 1 + len(cfg)
	}
	rest = bh - used
	chartH := max(7, min(14, rest*45/100))
	if rest-chartH < 7 {
		chartH = max(5, rest-7)
	}
	if rest >= 5 {
		out = append(out, m.chartPanel(w, min(chartH, rest)))
		used += min(chartH, rest)
	}
	if bh-used >= 3 {
		out = append(out, m.tradesPanel(w, bh-used))
	}
	return strings.Join(out, "\n")
}

// subRule: a small titled divider inside a panel ("WALLET ──────").
func (m *Model) subRule(title string, w int) string {
	t := m.th
	hr := m.g("─", "-")
	n := max(0, w-ansi.StringWidth(title)-1)
	return t.Acc.Render(title) + " " + t.Rule.Render(strings.Repeat(hr, n))
}

// overviewMedium (70..119 columns): the hero with the key figures beside it, one-line blocks, a short chart.
func (m *Model) overviewMedium(w, bh int) string {
	t := m.th
	v := m.view
	var out []string
	hero := m.heroLines(40, 3, false)
	hw := 0
	for _, l := range hero {
		hw = max(hw, ansi.StringWidth(l))
	}
	hw += 3
	ph := int64(0)
	if v.HasPerHour {
		ph = int64(v.PerHour)
	}
	ps, rg := v.PS, v.Reg
	psTxt := t.Lbl.Render("off")
	if ps.Active {
		psTxt = t.Money(ps.Net, true, false).Render(core.SolS(ps.Net)) + t.Lbl.Render(fmt.Sprintf("  %d fills %dW", ps.Fills, ps.Wins))
	}
	side := []string{
		t.PanelTitle.Render("RUN P&L") + "  " + m.toast(),
		m.kv("per hour", 10, m.money(ph, v.HasPerHour, 4)),
		m.kv("pre-send", 10, psTxt),
		m.kv("regular", 10, t.Money(rg.Total, true, false).Render(core.SolS(rg.Total))+t.Lbl.Render(fmt.Sprintf("  %d buys %d fills", rg.Fires, rg.Fills))),
	}
	suffix := ""
	if m.todayOn {
		suffix = " today"
	}
	if ath, low, _, fromShort, ok := m.athLines(10, suffix, w-hw); ok {
		if x := ath + "  " + fromShort; ansi.StringWidth(x) <= w-hw {
			ath = x
		}
		side = append(side, ath, low)
	}
	hh := max(len(hero), len(side))
	out = append(out, hcat(0, block(strings.Join(hero, "\n"), hw, hh), block(strings.Join(side, "\n"), w-hw, hh)))
	// run in one line: status, start -> end, elapsed / planned and the bar
	rl := m.runLines(w)
	runL := rl[0] + "   " + rl[1]
	if v.Planned.Truthy() {
		frac := v.SElapsed / (v.Planned.Float() * 60)
		el := t.Val.Render(core.Dur(v.SElapsed, v.HasSElapsed)) + t.Lbl.Render("/"+core.Dur(v.Planned.Float()*60, true))
		pct := t.Lbl.Render(fmt.Sprintf(" %.0f%%", math.Min(frac, 9.99)*100))
		gw := w - ansi.StringWidth(runL) - ansi.StringWidth(el) - ansi.StringWidth(pct) - 5
		if gw >= 6 {
			runL += "  " + el + "  " + m.bar(frac, min(gw, 30)) + pct
		}
	}
	out = append(out, cut(runL, w))
	if v.HasEstNow {
		x := m.kv("wallet", 8, m.bal(v.EstNow, true, 4, t.B))
		if v.HasKillDist {
			x += t.Lbl.Render("   kill sw. ") + t.Val.Render(core.F(float64(v.KillLevel)/core.LAM, 3)) + t.Lbl.Render(" "+m.g("·", "|")+" ") + t.Val.Render(core.F(float64(v.KillDist)/core.LAM, 3)) + t.Lbl.Render(" away")
		}
		if v.HasBudget {
			x += t.Lbl.Render("   budget ") + t.Val.Render(core.F(float64(v.BudgetLeft)/core.LAM, 3))
		}
		out = append(out, cut(x, w))
	}
	// the card in two lines
	ct, _ := m.cardTitle()
	cl := m.cardLines(w, true, 0)
	c := m.card()
	out = append(out, cut(t.AccB.Render(ct)+"  "+cl[0], w))
	out = append(out, cut(t.Lbl.Render("buy ")+t.Pos.Render(fmt.Sprint(c.Buys))+t.Lbl.Render(" / sell ")+t.Neg.Render(fmt.Sprint(c.Sells))+t.Dim.Render("   ")+cl[len(cl)-1], w))
	out = append(out, m.liveCompact(w))
	cfgN := 1
	if bh >= 28 {
		cfgN = 2
	}
	out = append(out, m.cfgStrip(w, cfgN)...)
	used := 0
	for _, x := range out {
		used += lines(x)
	}
	rest := bh - used
	chartH := 4
	switch {
	case rest >= 20:
		chartH = 8
	case rest >= 14:
		chartH = 6
	case rest >= 10:
		chartH = 5
	}
	if rest-chartH >= 4 {
		out = append(out, m.chartBlock(w, chartH, true))
		used += chartH
	}
	if bh-used > 1 {
		out = append(out, m.tradesBlock(w, bh-used))
	}
	return strings.Join(out, "\n")
}

// overviewNarrow (< 70 columns, phones): one column, the P&L first.
func (m *Model) overviewNarrow(w, bh int) string {
	t := m.th
	v := m.view
	var out []string
	rl := m.runLines(w)
	// the status and start -> end in one line (how it ended is in the end banner)
	st := t.StateDot(StatusState(v.Status), m.ascii) + " " + t.StatusStyle(v.Status).Render(v.Status) + "  "
	if x := st + rl[1]; ansi.StringWidth(x) <= w {
		out = append(out, x)
	} else {
		out = append(out, cut(rl[0], w), cut(rl[1], w))
	}
	out = append(out, m.heroLines(w, 3, false)...)
	ph := int64(0)
	if v.HasPerHour {
		ph = int64(v.PerHour)
	}
	out = append(out, m.kv("per hour", 9, m.money(ph, v.HasPerHour, 4)))
	ps, rg := v.PS, v.Reg
	pst := t.Lbl.Render("off")
	if ps.Active {
		pst = t.Money(ps.Net, true, false).Render(core.SolS(ps.Net))
	}
	out = append(out, m.kv("split", 9, t.Lbl.Render("PS ")+pst+t.Lbl.Render("  REG ")+t.Money(rg.Total, true, false).Render(core.SolS(rg.Total))))
	if v.HasEstNow {
		x := t.Lbl.Render(padRight("wallet", 9)) + t.B.Render(core.F(float64(v.EstNow)/core.LAM, 4))
		if v.HasKillDist {
			x += t.Lbl.Render("  kill ") + t.Val.Render(core.F(float64(v.KillDist)/core.LAM, 3)) + t.Lbl.Render(" away")
		}
		out = append(out, cut(x, w))
	}
	ct, _ := m.cardTitle()
	out = append(out, m.rule(ct, "", w))
	c := m.card()
	out = append(out, cut(t.Lbl.Render("profit ")+t.PosB.Render("+"+core.F(float64(c.Profit)/core.LAM, 4))+t.Lbl.Render("  loss ")+t.NegB.Render("-"+core.F(float64(c.Loss)/core.LAM, 4)), w))
	out = append(out, cut(t.Lbl.Render(fmt.Sprintf("buy %d / sell %d", c.Buys, c.Sells))+t.Lbl.Render("  net ")+t.Money(c.Net, true, true).Render(core.SolS(c.Net)), w))
	if ath, low, from, _, ok := m.athLines(9, "", w); ok {
		out = append(out, cut(ath, w), cut(low, w), cut(from, w))
	}
	ll := m.liveLines(w, true)
	out = append(out, cut(ll[0], w))
	used := len(out)
	rest := bh - used
	if rest >= 14 {
		out = append(out, m.configGrid(w, 2)...)
		used = len(out)
		rest = bh - used
	}
	if rest >= 9 {
		ch := 5
		if rest >= 14 {
			ch = 6
		}
		out = append(out, m.chartBlock(w, ch, true))
		used += ch
	}
	if bh-used > 1 {
		out = append(out, m.tradesBlock(w, bh-used))
	}
	return strings.Join(out, "\n")
}
