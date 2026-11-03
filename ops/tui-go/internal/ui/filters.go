package ui

// The Filters tab (8): what each pre-send filter blocked and what those blocks would have made (core/filters.go, the
// filters_report.py accounting). On top the table, one row per filter tagged LIVE (it changed what the engine did;
// scored on the shadow's paper = an estimate) or LOG (log only, would-have; scored on the real fills), with its net
// saved (green: saved us money, red: cost us); under it the skip list: every blocked item, sortable (o / O), filtered
// by filter (f), the unscored ones (no shadow fill) shown with n, c copies the mint, enter opens a LOG item's trade.

import (
	"fmt"
	"math"
	"sort"
	"strings"

	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/x/ansi"

	"dipmon/internal/core"
)

// fltSortKeys: the skip list's sort columns (o cycles, O flips; time = newest first by default).
var fltSortKeys = []string{"time", "filter", "kind", "mint", "result", "SOL"}

func lamOf(sol float64) int64 { return int64(math.Round(sol * 1e9)) }

// fltShort: a filter's name in at most 12 cells (phones).
func fltShort(key, name string) string {
	switch key {
	case "quiet":
		return "QUIET"
	case "create_slot":
		return "create-slot"
	case "young_age":
		return "age-1 skip"
	case "lone_whale":
		return "10-sec skip"
	case "deeper":
		return "deeper limit"
	case "gcr":
		if strings.Contains(name, "run only") {
			return "bad creator*"
		}
		return "bad creator"
	case "st":
		return "safe timer"
	case "ctx85":
		return "ctx85"
	case "grp":
		return "group risk"
	case "hc":
		return "holder clock"
	case "guard":
		return "landing guard"
	}
	return name
}

// fltCode: a LOG rule in 2 cells (a phone's skip list, several rules on one fill: "ST+GR+HC").
func fltCode(key string) string {
	switch key {
	case "gcr":
		return "BC"
	case "st":
		return "ST"
	case "ctx85":
		return "85"
	case "grp":
		return "GR"
	case "hc":
		return "HC"
	case "guard":
		return "LG"
	}
	return key
}

// fltChoices: the f cycle: all, LIVE, LOG, then each filter with something blocked.
func (m *Model) fltChoices() []string {
	out := []string{"all", "LIVE", "LOG"}
	if R := m.view.Filt; R != nil {
		for _, r := range R.Rows {
			if r.Blocked > 0 {
				out = append(out, r.Key)
			}
		}
	}
	return out
}

func (m *Model) fltChoiceName(c string) string {
	if R := m.view.Filt; R != nil {
		if r, ok := R.Row(c); ok {
			return r.Name
		}
	}
	return c
}

// fltItems: the skip list (filter, the unscored ones with n, sort).
func (m *Model) fltItems() ([]core.FiltItem, int) {
	items, hidden, _ := m.fltItems2()
	return items, hidden
}

// fltItems2: also the number of shadow-window rows hidden (v). A LIVE filter picked with f reveals its rows.
func (m *Model) fltItems2() ([]core.FiltItem, int, int) {
	R := m.view.Filt
	if R == nil {
		return nil, 0, 0
	}
	ch := m.fltChoices()
	c := ch[min(m.fltFilter, len(ch)-1)]
	var out []core.FiltItem
	hidden, shadow := 0, 0
	for _, it := range R.Items {
		if it.Live && !m.fltShadow && c == "all" { // the shadow-window rows: hidden by default (v); picking a LIVE filter with f reveals them
			shadow++
			continue
		}
		switch c {
		case "all":
		case "LIVE":
			if !it.Live {
				continue
			}
		case "LOG":
			if it.Live {
				continue
			}
		default: // one filter: a LOG fill shows under every rule that caught it
			if !it.Has(c) {
				continue
			}
		}
		if !it.Scored && !m.fltAll {
			hidden++
			continue
		}
		out = append(out, it)
	}
	key := fltSortKeys[m.fltSort]
	val := func(it core.FiltItem) (float64, string, bool) {
		switch key {
		case "filter":
			return 0, it.Name, true
		case "kind":
			return 0, it.Kind, true
		case "mint":
			return 0, strings.ToLower(it.Mint), it.Mint != ""
		case "result":
			if !it.Scored {
				return 0, "", false
			}
			if it.Sol > 0 {
				return 1, "", true
			}
			return -1, "", true
		case "SOL":
			return it.Sol, "", it.Scored
		}
		return float64(it.T), "", it.T != 0
	}
	sort.SliceStable(out, func(i, j int) bool {
		a, as, aok := val(out[i])
		b, bs, bok := val(out[j])
		if aok != bok {
			return aok // no value: last
		}
		if as != bs {
			if m.fltAsc {
				return as < bs
			}
			return as > bs
		}
		if a != b {
			if m.fltAsc {
				return a < b
			}
			return a > b
		}
		return false
	})
	return out, hidden, shadow
}

// tagLive / tagLog: the LIVE / LOG badges.
func (m *Model) fltTag(live bool, short bool) string {
	t := m.th
	if live {
		s := "LIVE"
		if short {
			s = "LV"
		}
		return t.AccB.Render(s)
	}
	s := "LOG"
	if short {
		s = "LG"
	}
	return t.Warn.Render(s)
}

// solCell: a SOL amount in green / red (3 decimals, signed).
func (m *Model) solCell(x float64, n int, bold bool) string {
	return m.th.Money(lamOf(x), n > 0 || x != 0, bold).Render(core.FS(x, 3))
}

// fltTableLines: the overview table, fitted to w.
func (m *Model) fltTableLines(w int) []string {
	t := m.th
	R := m.view.Filt
	short := w < 76
	nameW := min(24, w-58)
	if short {
		nameW = 13
	}
	note := w >= 110
	sep := t.Dim.Render(m.g("│", "|"))
	hdr := func() string {
		if short {
			return t.Lbl.Render(padRight("", 3) + padRight("filter", nameW) + " " + padLeft("blkd", 5) + " " + padLeft("W", 3) + " " + padLeft("L", 3) + " " + padLeft("net saved", 9))
		}
		s := padRight("", 5) + padRight("filter", nameW) + " " + padLeft("blocked", 7) + " " + m.g("│", "|") + " " + padLeft("would win", 13) + " " + m.g("│", "|") + " " +
			padLeft("would lose", 13) + " " + m.g("│", "|") + " " + padLeft("net saved", 9)
		if note {
			s += "   note"
		}
		return t.Lbl.Render(s)
	}
	row := func(r core.FiltRow) string {
		name := r.Name
		if ansi.StringWidth(name) > nameW {
			name = fltShort(r.Key, r.Name)
		}
		name = cut(name, nameW)
		if r.NA && short {
			return m.fltTag(false, true) + " " + t.Val.Render(padRight(name, nameW)) + " " + t.Dim.Render(padLeft("n/a", 5)+" dip30+")
		}
		if short {
			return m.fltTag(r.Type == "LIVE", true) + " " + t.Val.Render(padRight(name, nameW)) + " " + t.Val.Render(padLeft(core.IC(int64(r.Blocked)), 5)) + " " +
				t.Pos.Render(padLeft(fmt.Sprint(r.WinN), 3)) + " " + t.Neg.Render(padLeft(fmt.Sprint(r.LoseN), 3)) + " " +
				padLeft(m.solCell(r.Net(), r.WinN+r.LoseN, true), 9)
		}
		tag := m.fltTag(r.Type == "LIVE", false)
		if r.NA { // a rule this run does not log (the landing guard before dip30)
			return tag + strings.Repeat(" ", 5-ansi.StringWidth(tag)) + t.Val.Render(padRight(name, nameW)) + " " + t.Dim.Render(padLeft("n/a", 7)) + " " +
				t.Dim.Render("(dip30+: not logged by this run)")
		}
		s := tag + strings.Repeat(" ", 5-ansi.StringWidth(tag)) + t.Val.Render(padRight(name, nameW)) + " " + t.Val.Render(padLeft(core.IC(int64(r.Blocked)), 7)) + " " + sep + " " +
			t.Pos.Render(padLeft(fmt.Sprint(r.WinN), 4)) + " " + padLeft(m.solCell(r.WinSol, r.WinN, false), 8) + " " + sep + " " +
			t.Neg.Render(padLeft(fmt.Sprint(r.LoseN), 4)) + " " + padLeft(m.solCell(r.LoseSol, r.LoseN, false), 8) + " " + sep + " " +
			padLeft(m.solCell(r.Net(), r.WinN+r.LoseN, true), 9)
		if note {
			n := "real fills"
			if r.Type == "LIVE" {
				n = "paper estimate"
			}
			if r.Key == "gcr" && R.Seed == "" {
				n = "real fills; no seed: this run only"
			}
			if r.Key == "st" {
				n = "real fills; needs the safe on-chain check"
			}
			if r.Key == "grp" {
				n = "real fills; risky holders summed >= 6%"
			}
			if r.Key == "guard" {
				n = "real fills; signing-time set still holding"
			}
			s += "   " + t.Dim.Render(n)
		}
		return s
	}
	total := func(label string, x core.FiltTotal) string {
		if short {
			return t.Lbl.Render(padRight(label, 3+nameW)) + " " + t.B.Render(padLeft(core.IC(int64(x.Blocked)), 5)) + " " +
				t.Pos.Render(padLeft(fmt.Sprint(x.WinN), 3)) + " " + t.Neg.Render(padLeft(fmt.Sprint(x.LoseN), 3)) + " " + padLeft(m.solCell(x.Net, 1, true), 9)
		}
		return t.Lbl.Render(padRight(label, 5+nameW)) + " " + t.B.Render(padLeft(core.IC(int64(x.Blocked)), 7)) + " " + sep + " " +
			t.Pos.Render(padLeft(fmt.Sprint(x.WinN), 4)) + " " + padLeft(m.solCell(x.WinSol, x.WinN, false), 8) + " " + sep + " " +
			t.Neg.Render(padLeft(fmt.Sprint(x.LoseN), 4)) + " " + padLeft(m.solCell(x.LoseSol, x.LoseN, false), 8) + " " + sep + " " +
			padLeft(m.solCell(x.Net, 1, true), 9)
	}
	out := []string{hdr()}
	var logRows []core.FiltRow
	for _, r := range R.Rows {
		if r.Type != "LIVE" {
			logRows = append(logRows, r)
			continue
		}
		out = append(out, row(r))
		if r.Key == "deeper" && R.Deep { // the deep fills (bought >= 15% down): their real P&L vs the shadow's, the NET
			ind := strings.Repeat(" ", 5)
			if short {
				ind = "   "
			}
			d := t.Dim.Render(ind+m.g("└ ", "` ")) + t.Lbl.Render(fmt.Sprintf("%d deep fills: real ", R.DeepRealN)) + m.solCell(R.DeepReal, 1, false) +
				t.Lbl.Render(" vs 0.88x paper ") + m.solCell(R.DeepPaper, 1, false) + t.Lbl.Render(" = gain ") + m.solCell(R.DeepGain, 1, false) +
				t.Lbl.Render("  NET ") + m.solCell(R.DeepNet, 1, true)
			if w < 84 { // phones: the gain and the NET only
				d = t.Dim.Render(ind+m.g("└ ", "` ")) + t.Lbl.Render(fmt.Sprintf("%d deep fills gain ", R.DeepRealN)) + m.solCell(R.DeepGain, 1, false) +
					t.Lbl.Render("  NET ") + m.solCell(R.DeepNet, 1, true)
			}
			if R.DeepRAN > 0 && w >= 120 {
				d += t.Dim.Render(fmt.Sprintf("  (+%d re-arm deep fills ", R.DeepRAN)) + m.solCell(R.DeepRAReal, 1, false) + t.Dim.Render(", no shadow)")
			}
			out = append(out, d)
		}
	}
	lvLabel, lgLabel, allLabel := "LIVE total (unique triggers)", "LOG total (unique fills)", "ALL total"
	if ansi.StringWidth(lvLabel) > 5+nameW || short {
		lvLabel, lgLabel = "LIVE unique", "LOG unique"
	}
	lv := total(lvLabel, R.LiveU)
	if R.Deep && w >= 110 { // the deeper limit's deep fills earned apart from its blocks
		lv += t.Dim.Render("   with the deep fills' gain ") + m.solCell(R.LiveU.Net+R.DeepGain, 1, true)
	}
	if R.LiveDup > 0 && w >= 100 {
		lv += t.Dim.Render(fmt.Sprintf("   rows sum %d more: a trigger under 2+ rows", R.LiveDup))
	}
	out = append(out, lv)
	for _, r := range logRows {
		out = append(out, row(r))
	}
	lt := total(lgLabel, R.LogU)
	if w >= 100 {
		lt += t.Dim.Render(fmt.Sprintf("   each fill once; %d fills hit 2+ rules (rows sum %d more)", R.LogMulti, R.LogDup))
	}
	out = append(out, lt)
	at := total(allLabel, R.All)
	if w >= 100 {
		at += t.Dim.Render("   LIVE is paper, LOG is real fills; disjoint sets; estimate")
	}
	out = append(out, at)
	return out
}

// scrFilters: the table, then the skip list (scrolls with its selection, like Trades).
func (m *Model) scrFilters(w, bh int) string {
	t := m.th
	R := m.view.Filt
	if R == nil || !R.Any {
		m.fltRows = nil
		m.fltRowY = 0
		return m.rule("FILTERS", "", w) + "\n" + t.Lbl.Render("no filter records in this run (pre-send skips, deeper-limit tries, annotations)")
	}
	sep := t.Dim.Render(" " + m.g("·", "|") + " ")
	var out []string
	right := m.fltTag(true, false) + t.Lbl.Render(" changed what the engine did (paper)") + sep + m.fltTag(false, false) + t.Lbl.Render(" log only, would-have (real fills)")
	if w < 100 {
		right = m.fltTag(true, false) + t.Lbl.Render(" live") + sep + m.fltTag(false, false) + t.Lbl.Render(" log only")
	}
	out = append(out, m.rule("FILTERS", right, w))
	out = append(out, m.fltTableLines(w)...)
	foot := t.Dim.Render("net saved = minus what the blocked would have made: ") + t.Pos.Render("green saved us") + t.Dim.Render(", ") + t.Neg.Render("red cost us")
	if w >= 120 {
		seed := "bad creator: no ledger seed (this run's fills only)"
		if R.Seed != "" {
			seed = fmt.Sprintf("bad creator ledger: %d creators seeded", R.SeedN)
		}
		foot += t.Dim.Render("   " + seed)
		if R.RearmSkips > 0 {
			foot += t.Dim.Render(fmt.Sprintf("; re-arm skips %s not scored (no shadow)", core.IC(R.RearmSkips)))
		}
	}
	out = append(out, foot)
	// the skip list
	items, hidden, shadowHid := m.fltItems2()
	m.fltRows = items
	n := len(items)
	if n == 0 {
		m.fltSel = 0
	} else {
		m.fltSel = max(0, min(m.fltSel, n-1))
	}
	ch := m.fltChoices()
	m.fltFilter = min(m.fltFilter, len(ch)-1)
	var wins, loses int
	var sum float64
	for _, it := range items {
		if it.Scored {
			sum += it.Sol
			if it.Sol > 0 {
				wins++
			} else {
				loses++
			}
		}
	}
	left := t.Acc.Render(m.fltChoiceName(ch[m.fltFilter])) + t.Lbl.Render(fmt.Sprintf("  (%s)", core.IC(int64(n))))
	if !(fltSortKeys[m.fltSort] == "time" && !m.fltAsc) {
		arrow := m.g("▼", "v")
		if m.fltAsc {
			arrow = m.g("▲", "^")
		}
		left += t.Lbl.Render("  sort ") + t.Acc.Render(fltSortKeys[m.fltSort]+" "+arrow)
	}
	if hidden > 0 {
		left += t.Dim.Render(fmt.Sprintf("  +%s no fill (n)", core.IC(int64(hidden))))
	} else if m.fltAll {
		left += t.Dim.Render("  with no-fill (n)")
	}
	if shadowHid > 0 {
		left += t.Dim.Render(fmt.Sprintf("  +%s shadow (v)", core.IC(int64(shadowHid))))
	} else if m.fltShadow {
		left += t.Dim.Render("  with shadow (v)")
	}
	rt := t.Pos.Render(fmt.Sprintf("%dW", wins)) + t.Lbl.Render(" ") + t.Neg.Render(fmt.Sprintf("%dL", loses)) + t.Lbl.Render("  ") + m.solCell(sum, 1, false)
	if w >= 110 {
		rt += t.Dim.Render("   f filter  n no-fill  v shadow  o sort  O order  c copy")
	}
	out = append(out, m.rule("SKIPPED / BLOCKED", "", w))
	out = append(out, lr(left, rt, w))
	rowsAvail := bh - len(out)
	if rowsAvail < 3 { // a short terminal: the list keeps 3 rows, the table gives way
		drop := 3 - rowsAvail
		head := out[:len(out)-2]
		if drop < len(head) {
			head = head[:len(head)-drop]
		} else {
			head = head[:1]
		}
		out = append(append([]string(nil), head...), out[len(out)-2:]...)
		rowsAvail = max(1, bh-len(out))
	}
	rowsAvail-- // the header
	if rowsAvail < 1 {
		rowsAvail = 1
	}
	if m.fltSel < m.fltTop {
		m.fltTop = m.fltSel
	}
	if m.fltSel >= m.fltTop+rowsAvail {
		m.fltTop = m.fltSel - rowsAvail + 1
	}
	m.fltTop = max(0, min(m.fltTop, max(0, n-rowsAvail)))
	if n == 0 {
		out = append(out, t.Lbl.Render("nothing blocked here"+map[bool]string{true: " that would have filled (n shows the rest)", false: ""}[hidden > 0]))
		m.fltRowY = 0
		return strings.Join(out, "\n")
	}
	m.fltRowY = m.bodyY + len(out) + 1
	vis := items[m.fltTop:min(n, m.fltTop+rowsAvail)]
	out = append(out, m.fltList(w, vis, m.fltSel-m.fltTop))
	if n > rowsAvail {
		m.moreHint = fmt.Sprintf("%d/%d", m.fltSel+1, n)
	}
	return strings.Join(out, "\n")
}

// fltList: the skip list's rows (a header, the selection, zebra rows like Trades).
func (m *Model) fltList(w int, rows []core.FiltItem, sel int) string {
	t := m.th
	type col struct {
		title string
		w     int
		right bool
	}
	mintW := 8
	if w >= 150 {
		mintW = 44
	}
	var cols []col
	switch {
	case w >= 90: // the filter column: up to 42 cells (a LOG fill's every rule), the note keeps >= 12
		fw := max(22, min(42, w-(1+11+4+4+mintW+6+8+9)-12))
		cols = []col{{"", 1, false}, {"time", 11, true}, {"type", 4, false}, {"filter", fw, false}, {"kind", 4, false}, {"mint", mintW, false}, {"result", 6, false}, {"SOL", 8, true}, {"", 0, false}}
	case w >= 66:
		cols = []col{{"", 1, false}, {"time", 11, true}, {"type", 4, false}, {"filter", 16, false}, {"kind", 4, false}, {"mint", 8, false}, {"result", 6, false}, {"SOL", 8, true}}
	default:
		cols = []col{{"", 1, false}, {"time", 11, true}, {"ty", 2, false}, {"filter", 10, false}, {"mint", 6, false}, {"res", 4, false}, {"SOL", 7, true}}
	}
	fixed := 0
	for _, c := range cols {
		fixed += c.w + 1
	}
	if last := &cols[len(cols)-1]; last.w == 0 {
		last.w = max(1, w-fixed)
	}
	cell := func(s string, c col) string {
		s = ansi.Truncate(s, c.w, "…")
		if c.right {
			return padLeft(s, c.w)
		}
		return padRight(s, c.w)
	}
	var b strings.Builder
	for i, c := range cols {
		h := c.title
		if sortKeyFlt(c.title) == fltSortKeys[m.fltSort] && h != "" {
			arrow := m.g("▼", "v")
			if m.fltAsc {
				arrow = m.g("▲", "^")
			}
			h = arrow + h
		}
		st := t.Lbl
		if sortKeyFlt(c.title) == fltSortKeys[m.fltSort] && h != "" {
			st = t.Acc.Bold(true)
		}
		b.WriteString(st.Render(cell(h, c)))
		if i < len(cols)-1 {
			b.WriteString(" ")
		}
	}
	lines := []string{b.String()}
	for i, it := range rows {
		var parts []string
		for _, c := range cols {
			var s string
			st := t.Val
			switch c.title {
			case "":
				if c.w == 1 && i == sel {
					s = m.g("▸", ">")
				}
				if c.w != 1 {
					st = t.Dim
					if !it.Live {
						s = "real fill"
						if it.Has("guard") {
							s = fmt.Sprintf("real fill; guard set %.1f%% at landing", it.GuardPct)
						}
					} else if it.Filter == "deeper" {
						s = "shadow window of the trigger"
					} else {
						s = "shadow window"
					}
				}
			case "time":
				st = t.Lbl
				if it.T != 0 {
					s = core.T12(float64(it.T), true)
				}
			case "type", "ty":
				tag := "LIVE"
				if !it.Live {
					tag = "LOG"
				}
				if c.w == 2 {
					tag = map[bool]string{true: "LV", false: "LG"}[it.Live]
				}
				s = tag
				st = t.Warn
				if it.Live {
					st = t.AccB
				}
			case "filter": // a LOG fill: every rule that would have blocked it
				s = it.Name
				if ansi.StringWidth(s) > c.w {
					sh := make([]string, len(it.Rules))
					for j, r := range it.Rules {
						sh[j] = fltShort(r, it.Names[j])
					}
					s = strings.Join(sh, ", ")
				}
				if ansi.StringWidth(s) > c.w && len(it.Rules) > 1 { // narrow: the first rule + how many more, else the codes
					s = fmt.Sprintf("%s +%d", fltShort(it.Rules[0], it.Names[0]), len(it.Rules)-1)
					if ansi.StringWidth(s) > c.w {
						cs := make([]string, len(it.Rules))
						for j, r := range it.Rules {
							cs[j] = fltCode(r)
						}
						s = strings.Join(cs, "+")
					}
				}
			case "kind":
				s, st = it.Kind, t.Lbl
				if it.Kind == "RA" {
					st = t.Acc
				}
			case "mint":
				s = core.Short(it.Mint, c.w)
			case "result", "res":
				switch {
				case !it.Scored:
					s, st = "no fill", t.Dim
					if c.w == 4 {
						s = "—"
					}
				case it.Sol > 0:
					s, st = "WIN", t.Pos
				default:
					s, st = "LOSE", t.Neg
				}
			case "SOL":
				if it.Scored {
					s, st = core.FS(it.Sol, 4), t.Money(lamOf(it.Sol), true, false)
					if c.w < 8 {
						s = core.FS(it.Sol, 3)
					}
				} else {
					s, st = core.G.Dash, t.Dim
				}
			}
			txt := cell(s, c)
			if c.title == "mint" && m.linksOn() && it.Mint != "" { // OSC 8: the mint opens GMGN
				st = st.Hyperlink(gmgnURL(it.Mint))
			}
			if !t.Mono && i%2 == 1 {
				st = st.Background(t.Zebra)
			}
			if i == sel {
				st = st.Background(t.SelBg).Bold(true)
				if t.Mono {
					st = st.Reverse(true)
				}
			}
			parts = append(parts, st.Render(txt))
		}
		sp := lipgloss.NewStyle()
		if !t.Mono && i%2 == 1 {
			sp = sp.Background(t.Zebra)
		}
		if i == sel {
			sp = sp.Background(t.SelBg)
		}
		lines = append(lines, strings.Join(parts, sp.Render(" ")))
	}
	return strings.Join(lines, "\n")
}

func sortKeyFlt(title string) string {
	switch title {
	case "ty", "type":
		return "" // LIVE / LOG: the filter sort groups them
	case "res", "result":
		return "result"
	}
	return title
}

// fltTrade: the LOG item's position in the trades (enter opens its details); nil for a LIVE item.
func (m *Model) fltTrade(it core.FiltItem) *core.Trade {
	if it.Live {
		return nil
	}
	for _, tr := range m.view.Trades {
		if tr.Kind == "PS" && tr.Mint == it.Mint && tr.W.Ok && tr.W.W == it.W {
			return tr
		}
	}
	return nil
}
