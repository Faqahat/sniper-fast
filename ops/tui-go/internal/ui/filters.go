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
	case "breaker":
		return "breaker"
	case "cr_loss":
		return "creator loss"
	case "cr_unfollowed":
		return "cr unfollowed"
	case "quiet3_a":
		return "QUIET3-A live"
	case "q3a":
		return "QUIET3-A"
	case "fresh":
		return "fresh holders"
	case "crlog":
		return "creator loss (log)"
	case "eqgrp":
		return "equal group"
	case "fam":
		return "fam"
	case "fpnb":
		return "no-bot (log)"
	case "skip2":
		return "skip2 (log)"
	case "fpnb_live":
		return "no-bot (live)"
	case "blocklist":
		return "blocklist"
	case "wh_loss":
		return "whale loss"
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
	case "q3a":
		return "Q3"
	case "fresh":
		return "FH"
	case "crlog":
		return "CL"
	case "eqgrp":
		return "EQ"
	case "fam":
		return "FM"
	case "fpnb":
		return "NB"
	case "skip2":
		return "S2"
	case "fpnb_live":
		return "NL"
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
			if !it.Scored { // a LIVE skip whose shadow window never filled: no dip, between WIN and LOSE
				return 0, "", it.Live
			}
			if it.Sol > 0 {
				return 1, "", true
			}
			return -1, "", true
		case "SOL":
			return it.Sol, "", it.Scored || it.Live // no dip = 0.000 (Sol is 0)
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

// invCell: what blocked trades would have made, colored from the FILTER's side (owner 11-03: "green good, red bad"): a blocked
// winner (+) cost us (red), a blocked loser (-) saved us (green). The number itself keeps its sign.
func (m *Model) invCell(x float64, n int, bold bool) string {
	return m.th.Money(lamOf(-x), n > 0 || x != 0, bold).Render(core.FS(x, 3))
}

// fltVerdict: a filter's verdict from the FILTERS-3 study (11-03 PKT: ops/strategies/presend/filters3/tune/tune.json
// "verdicts" and build/DIP32.md). group orders the table (LIVE, then LOG, then DISMISSED, folded into one line).
type fltVerdict struct {
	group      int    // vgLive / vgLog / vgDism
	label, why string // the verdict (<= 10 cells) and a 3-6 word reason
}

const (
	vgLive = iota
	vgLog
	vgDism
)

// fltVerdicts: the one place to edit the verdicts (key = the row's Key, core/filters.go).
var fltVerdicts = map[string]fltVerdict{
	"create_slot":   {vgLive, "KEEP", "strongest, + always"},
	"quiet":         {vgLive, "KEEP", "small + everywhere"},
	"young_age":     {vgLive, "KEEP", "no value either way"},
	"lone_whale":    {vgLive, "KEEP", "tiny + everywhere"},
	"breaker":       {vgLive, "LIVE new", "fires on attacks"},
	"cr_loss":       {vgLive, "LIVE new", "+ in every period"},
	"quiet3_a":      {vgLive, "LIVE new", "dead token + new whale; attack"},
	"cr_unfollowed": {vgLog, "LOG", "unproven vs ledger"},
	"gcr":           {vgLive, "LIVE dip32", "now creator loss"},
	"grp":           {vgLog, "LOG", "weak, keep logging"},
	"q3a":           {vgLog, "LOG", "weak on holdout"},
	"fresh":         {vgLog, "LOG", "attack guard (G3)"},
	"crlog":         {vgLog, "LOG", "ledger off: would-skips"},
	"eqgrp":         {vgLog, "LOG", "mixed r51/r53"},
	"fam":           {vgLog, "LOG new", "bundle rug (dip35)"},
	"fpnb":          {vgLog, "LOG new", "no follower bot (dip36)"},
	"skip2":         {vgLog, "LOG new", "per-send logit (dip36)"},
	"fpnb_live":     {vgLive, "LIVE new", "no-bot gate (dip36)"},
	"blocklist":     {vgLive, "LIVE new", "listed wallets (dip36)"},
	"wh_loss":       {vgLive, "LIVE new", "whale/dumper ledger (dip37)"},
	"st":            {vgDism, "DISMISSED", "within group risk"},
	"hc":            {vgDism, "DISMISSED", "dup of group risk"},
	"guard":         {vgDism, "DISMISSED", "flagged did better"},
	"ctx85":         {vgDism, "DISMISSED", "attack-only gain"},
}

// fltVerdictOf: the row's verdict; a filter the study did not judge (the deeper limit) keeps its type's group, "—".
func fltVerdictOf(r core.FiltRow) fltVerdict {
	if v, ok := fltVerdicts[r.Key]; ok {
		return v
	}
	if r.Type == "LIVE" {
		return fltVerdict{vgLive, core.G.Dash, "no 11-03 verdict"}
	}
	return fltVerdict{vgLog, core.G.Dash, "no 11-03 verdict"}
}

// fltVerdictShort: the verdict in 4 cells (phones).
func fltVerdictShort(label string) string {
	switch label {
	case "LIVE new":
		return "NEW"
	case "LIVE dip32":
		return "LV32"
	case "DISMISSED":
		return "DISM"
	}
	return label
}

func (m *Model) verdictStyle(v fltVerdict) lipgloss.Style {
	t := m.th
	switch {
	case v.label == core.G.Dash:
		return t.Dim
	case v.group == vgLive:
		return t.Good
	case v.group == vgLog:
		return t.Warn
	}
	return t.Dim
}

// fltPrec: the precision of a row: the losers among the marked items that have a value (%), ok = any.
func fltPrec(winN, loseN int) (float64, bool) {
	if winN+loseN == 0 {
		return 0, false
	}
	return float64(loseN) / float64(winN+loseN) * 100, true
}

// precCell: the precision in n cells, green >= 60%, yellow >= 50% (a coin flip), red below.
func (m *Model) precCell(winN, loseN, n int) string {
	t := m.th
	p, ok := fltPrec(winN, loseN)
	if !ok {
		return t.Dim.Render(padLeft(core.G.Dash, n))
	}
	st := t.Neg
	switch {
	case p >= 60:
		st = t.Pos
	case p >= 50:
		st = t.Warn
	}
	return st.Render(padLeft(fmt.Sprintf("%.0f%%", p), n))
}

// fltSortedRows: the table's rows by verdict group (LIVE, LOG, DISMISSED), within a group by net saved (largest first;
// a rule this run does not log last), the table's own order on ties.
func fltSortedRows(rows []core.FiltRow) []core.FiltRow {
	out := append([]core.FiltRow(nil), rows...)
	sort.SliceStable(out, func(i, j int) bool {
		a, b := out[i], out[j]
		ga, gb := fltVerdictOf(a).group, fltVerdictOf(b).group
		if ga != gb {
			return ga < gb
		}
		if a.NA != b.NA {
			return !a.NA
		}
		return lamOf(a.Net()) > lamOf(b.Net())
	})
	return out
}

// fltTableLines: the overview table, fitted to w: tag, filter, verdict, NET SAVED, precision, then blocked and the
// would-win / would-lose (wide), the reason; the DISMISSED filters folded into one line (d expands), the unique totals.
func (m *Model) fltTableLines(w int) []string {
	t := m.th
	R := m.view.Filt
	bar := " " + m.g("│", "|") + " "
	sep := t.Dim.Render(bar)
	// three layouts: wide (the would-win / would-lose sums, the reason), medium (counts only), phones (4-cell verdicts)
	mode := 2
	switch {
	case w >= 100:
		mode = 0
	case w >= 76:
		mode = 1
	}
	var nameW, tagW, vdW, netW, precW int
	showBlk, showWL := true, true
	switch mode {
	case 0:
		tagW, vdW, netW, precW = 5, 10, 9, 5
		nameW = min(24, w-74)
	case 1:
		tagW, vdW, netW, precW = 5, 10, 9, 5
		nameW = min(24, w-52)
	default:
		tagW, vdW, netW, precW = 3, 4, 8, 4
		nameW = 13
		fixed := tagW + nameW + 1 + vdW + 1 + netW + 1 + precW // 35
		if fixed+6+8 > w {
			showWL = false
		}
		if fixed+6 > w {
			showBlk = false
		}
		if fixed > w {
			nameW = max(4, nameW-(fixed-w))
		}
	}
	whyW := 0
	if mode == 0 {
		whyW = w - (74 + nameW) - 3
		if whyW < 12 {
			whyW = 0
		}
	}
	// the numbers after the name + verdict (net, prec, blocked, W / L), shared by the rows, the totals and the folded line
	nums := func(net string, winN, loseN, blocked int, winSol, loseSol float64, bold bool) string {
		s := " " + padLeft(net, netW) + " " + m.precCell(winN, loseN, precW)
		blk := core.IC(int64(blocked))
		st := t.Val
		if bold {
			st = t.B
		}
		switch mode {
		case 0:
			s += sep + st.Render(padLeft(blk, 7)) + sep + t.Neg.Render(padLeft(fmt.Sprint(winN), 4)) + " " + padLeft(m.invCell(winSol, winN, false), 8) + sep +
				t.Pos.Render(padLeft(fmt.Sprint(loseN), 4)) + " " + padLeft(m.invCell(loseSol, loseN, false), 8)
		case 1:
			s += sep + st.Render(padLeft(blk, 7)) + " " + t.Neg.Render(padLeft(fmt.Sprint(winN), 4)) + " " + t.Pos.Render(padLeft(fmt.Sprint(loseN), 4))
		default:
			if showBlk {
				s += " " + st.Render(padLeft(blk, 5))
			}
			if showWL {
				s += " " + t.Neg.Render(padLeft(fmt.Sprint(winN), 3)) + " " + t.Pos.Render(padLeft(fmt.Sprint(loseN), 3))
			}
		}
		return s
	}
	hdr := func() string {
		s := padRight("", tagW) + padRight("filter", nameW) + " " + padRight("verdict", vdW) + " " + padLeft("net saved", netW) + " " + padLeft("prec", precW)
		switch mode {
		case 0:
			s += bar + padLeft("blocked", 7) + bar + padLeft("would win", 13) + bar + padLeft("would lose", 13)
			if whyW > 0 {
				s += "   why"
			}
		case 1:
			s += bar + padLeft("blocked", 7) + " " + padLeft("W", 4) + " " + padLeft("L", 4)
		default:
			s = padRight("", tagW) + padRight("filter", nameW) + " " + padRight("vrdt", vdW) + " " + padLeft("net", netW) + " " + padLeft("prec", precW)
			if showBlk {
				s += " " + padLeft("blkd", 5)
			}
			if showWL {
				s += " " + padLeft("W", 3) + " " + padLeft("L", 3)
			}
		}
		return t.Lbl.Render(s)
	}
	row := func(r core.FiltRow) string {
		name := r.Name
		if ansi.StringWidth(name) > nameW {
			name = fltShort(r.Key, r.Name)
		}
		name = cut(name, nameW)
		vd := fltVerdictOf(r)
		tag := m.fltTag(r.Type == "LIVE", mode == 2)
		lbl := vd.label
		if mode == 2 {
			lbl = fltVerdictShort(lbl)
		}
		s := tag + strings.Repeat(" ", max(0, tagW-ansi.StringWidth(tag))) + t.Val.Render(padRight(name, nameW)) + " " + m.verdictStyle(vd).Render(padRight(cut(lbl, vdW), vdW))
		if r.NA { // a rule this run does not log (the landing guard before dip30)
			if mode == 2 {
				return s + " " + t.Dim.Render(padLeft("n/a", netW)+" dip30+")
			}
			return s + " " + t.Dim.Render(padLeft("n/a", netW)) + "  " + t.Dim.Render("(dip30+: not logged by this run)")
		}
		s += nums(m.solCell(r.Net(), r.WinN+r.LoseN, true), r.WinN, r.LoseN, r.Blocked, r.WinSol, r.LoseSol, false)
		if whyW > 0 {
			why := vd.why
			if r.Key == "gcr" && R.Seed == "" {
				why = "no seed: this run only; " + why
			}
			s += "   " + t.Dim.Render(cut(why, whyW))
		}
		return s
	}
	lead := tagW + nameW + 1 + vdW // the label span of a total / the folded line
	total := func(label string, x core.FiltTotal) string {
		return t.Lbl.Render(padRight(cut(label, lead), lead)) + nums(m.solCell(x.Net, 1, true), x.WinN, x.LoseN, x.Blocked, x.WinSol, x.LoseSol, true)
	}
	deepLine := func() string { // the deeper limit's deep fills (bought >= 15% down): their real P&L vs the shadow's, the NET
		ind := strings.Repeat(" ", tagW)
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
		return d
	}
	out := []string{hdr()}
	var dism []core.FiltRow
	for _, r := range fltSortedRows(R.Rows) {
		if fltVerdictOf(r).group == vgDism {
			dism = append(dism, r)
			continue
		}
		out = append(out, row(r))
		if r.Key == "deeper" && R.Deep {
			out = append(out, deepLine())
		}
	}
	if len(dism) > 0 { // the DISMISSED filters: one line (count, the rows' net summed), d expands them under it
		var net float64
		var names []string
		var winN, loseN, blocked int
		var winSol, loseSol float64
		for _, r := range dism {
			names = append(names, fltShort(r.Key, r.Name))
			if !r.NA {
				net += r.Net()
				winN, loseN, blocked = winN+r.WinN, loseN+r.LoseN, blocked+r.Blocked
				winSol, loseSol = winSol+r.WinSol, loseSol+r.LoseSol
			}
		}
		arrow, act := m.g("▸", ">"), "show"
		if m.fltDism {
			arrow, act = m.g("▾", "v"), "hide"
		}
		label := fmt.Sprintf("%s %d DISMISSED  d %s", arrow, len(dism), act)
		if mode == 2 {
			label = fmt.Sprintf("%s %d dismissed (d)", arrow, len(dism))
		}
		l := t.Dim.Render(padRight(cut(label, lead), lead)) + nums(m.solCell(net, winN+loseN, true), winN, loseN, blocked, winSol, loseSol, false)
		if whyW > 0 {
			l += "   " + t.Dim.Render(cut(strings.Join(names, ", "), whyW))
		}
		out = append(out, l)
		if m.fltDism {
			for _, r := range dism {
				out = append(out, row(r))
			}
		}
	}
	lvLabel, lgLabel, allLabel := "LIVE total (unique triggers)", "LOG total (unique fills)", "ALL total"
	if ansi.StringWidth(lvLabel) > lead {
		lvLabel, lgLabel = "LIVE unique", "LOG unique"
	}
	lv := total(lvLabel, R.LiveU)
	tail := func(s string) string { // a total's dim note in the reason column (wide only)
		if whyW > 0 {
			return "   " + t.Dim.Render(cut(s, whyW))
		}
		return ""
	}
	addIf := func(line, x string) string { // x only when the line keeps within w
		if ansi.StringWidth(line)+ansi.StringWidth(x) <= w {
			return line + x
		}
		return line
	}
	if R.Deep && whyW > 0 { // the deeper limit's deep fills earned apart from its blocks
		lv = addIf(lv, t.Dim.Render("   incl. deep ")+m.solCell(R.LiveU.Net+R.DeepGain, 1, true))
	} else if R.LiveDup > 0 {
		lv += tail(fmt.Sprintf("%d triggers in 2+ rows", R.LiveDup))
	}
	out = append(out, lv)
	out = append(out, total(lgLabel, R.LogU)+tail(fmt.Sprintf("%d fills in 2+ rules", R.LogMulti)))
	out = append(out, total(allLabel, R.All)+tail("LIVE paper+LOG real"))
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
	// the legend: what net saved / prec / verdict mean (one line), then (wide) how LIVE and LOG rows are scored
	foot := t.Dim.Render("net saved = "+m.g("−", "-")+"(what the blocked would have made): ") + t.Pos.Render("green saved") + t.Dim.Render(", ") + t.Neg.Render("red cost") + sep +
		t.Dim.Render("prec = losers / marked") + sep + t.Dim.Render("verdict: FILTERS-3 11-03")
	if w < 120 {
		foot = t.Dim.Render("net saved: ") + t.Pos.Render("green saved") + t.Dim.Render(", ") + t.Neg.Render("red cost") + sep + t.Dim.Render("prec = losers / marked") + sep +
			t.Dim.Render("verdict 11-03")
	}
	out = append(out, cut(foot, w))
	if w >= 120 {
		leg := "LIVE rows: paper; blocked = triggers skipped, W/L = the ones that would have filled · LOG rows: real fills"
		seed := "bad creator: no ledger seed (this run's fills only)"
		if R.Seed != "" {
			seed = fmt.Sprintf("bad creator ledger: %d creators seeded", R.SeedN)
		}
		leg += " · " + seed
		if R.RearmSkips > 0 {
			leg += fmt.Sprintf("; re-arm skips %s not scored (no shadow)", core.IC(R.RearmSkips))
		}
		if m.ascii {
			leg = strings.ReplaceAll(leg, "·", "|")
		}
		out = append(out, t.Dim.Render(cut(leg, w)))
	}
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
		left += t.Dim.Render(fmt.Sprintf("  +%s no dip (n)", core.IC(int64(hidden))))
	} else if m.fltAll {
		left += t.Dim.Render("  with no-dip (n)")
	}
	if shadowHid > 0 {
		left += t.Dim.Render(fmt.Sprintf("  +%s shadow (v)", core.IC(int64(shadowHid))))
	} else if m.fltShadow {
		left += t.Dim.Render("  with shadow (v)")
	}
	rt := t.Neg.Render(fmt.Sprintf("%dW", wins)) + t.Lbl.Render(" ") + t.Pos.Render(fmt.Sprintf("%dL", loses)) + t.Lbl.Render("  ") + m.invCell(sum, 1, false)
	if w >= 110 {
		rt += t.Dim.Render("   f filter  n no-dip  v shadow  o sort  O order  c copy")
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

// fltMove: a LIVE row's shadow-window price move, max / min vs the trigger's post price, rounded ("+35/-8%", "+4/0%"); "–" when the
// record has no "move" (runs before 11-03), "0 trades" when nothing traded in the window.
func fltMove(mv *core.FMove) string {
	if mv == nil {
		return core.G.Dash
	}
	if mv.N == 0 {
		return "0 trades"
	}
	r := func(x float64) string { // rounded, signed; 0 unsigned
		if v := int(math.Round(x)); v != 0 {
			return fmt.Sprintf("%+d", v)
		}
		return "0"
	}
	return r(mv.Max) + "/" + r(mv.Min) + "%"
}

// fltList: the skip list's rows (a header, the selection, zebra rows like Trades). The move column (a LIVE row's
// shadow-window price move) when the list has a LIVE row and the width allows (>= 76 cells).
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
	showMove := false
	for _, it := range m.fltRows {
		if it.Live {
			showMove = true
			break
		}
	}
	moveW := 0
	if showMove {
		moveW = 10 // 9 cells + the gap
	}
	var cols []col
	switch {
	case w >= 90: // the filter column: up to 42 cells (a LOG fill's every rule), the note keeps >= 12
		fw := max(22, min(42, w-(1+11+4+4+mintW+6+8+9+moveW)-12))
		cols = []col{{"", 1, false}, {"time", 11, true}, {"type", 4, false}, {"filter", fw, false}, {"kind", 4, false}, {"mint", mintW, false}, {"result", 6, false}, {"SOL", 8, true}}
		if showMove {
			cols = append(cols, col{"move", 9, true})
		}
		cols = append(cols, col{"", 0, false})
	case w >= 66:
		cols = []col{{"", 1, false}, {"time", 11, true}, {"type", 4, false}, {"filter", 16, false}, {"kind", 4, false}, {"mint", 8, false}, {"result", 6, false}, {"SOL", 8, true}}
		if showMove && w >= 76 {
			cols = append(cols, col{"move", 9, true})
		}
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
				case !it.Scored: // a LIVE skip whose shadow window never filled: the trade would not have happened
					s, st = "no dip", t.Dim
					if c.w == 4 {
						s = core.G.Dash
					}
				case it.Sol > 0: // a blocked winner: the filter cost us (red); a blocked loser: it saved us (green)
					s, st = "WIN", t.Neg
				default:
					s, st = "LOSE", t.Pos
				}
			case "SOL":
				if it.Scored {
					s, st = core.FS(it.Sol, 4), t.Money(lamOf(-it.Sol), true, false)
					if c.w < 8 {
						s = core.FS(it.Sol, 3)
					}
				} else if it.Live { // no dip: nothing saved or lost
					s, st = "0.000", t.Dim
				} else {
					s, st = core.G.Dash, t.Dim
				}
			case "move": // LIVE rows only: the shadow window's price move
				if it.Live {
					s, st = fltMove(it.Move), t.Lbl
					if it.Move == nil || it.Move.N == 0 {
						st = t.Dim
					}
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
