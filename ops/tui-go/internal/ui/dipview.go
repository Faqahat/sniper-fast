package ui

// dipview: the run explorer. Left, every run in the runs directory (dip_rN / dip_ams_rN, .jsonl and / or .log): the
// run, its engine, start → end (PKT, 12-hour) and a green (running) or grey (ended) dot; right, the selected run's
// overview (result in SOL / USD, fills, wins, the pre-send / regular split, duration, the key config). Enter opens
// the run in dipmon; quitting dipmon comes back here. Read-only, like dipmon: the run files and /proc, nothing else.
// Each run's numbers come from the same accounting as dipmon (core.BuildView), computed in the background at low
// priority, one run at a time (the selected one first), and kept as a few numbers (finished runs once; a running run
// is followed incrementally while it runs).

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	tea "charm.land/bubbletea/v2"
	"github.com/charmbracelet/x/ansi"

	"dipmon/internal/core"
)

var runFileRX = regexp.MustCompile(`^dip_(ams_)?r(\d+)\.(jsonl|log)$`)

// RunEntry is one run in the directory.
type RunEntry struct {
	Tag     string // dip_r27 / dip_ams_r27
	Region  string // FRA / AMS
	N       int
	JSONL   string // the records path (may not exist: a log-only run)
	Log     string
	HasJ    bool
	Size    int64
	MTime   time.Time
	T0      int64 // run_start t (ns), 0 = unknown
	Running bool  // an engine process writes it (its --dip-log)
}

// Name: "FRA r27".
func (r RunEntry) Name() string { return r.Region + " r" + strconv.Itoa(r.N) }

// RunSum: the few numbers the explorer shows for a run (the dipmon accounting, to the lamport).
type RunSum struct {
	Key                                string // size|mtime when computed (a finished run is not computed again)
	At                                 time.Time
	Status, HowEnded, Build            string
	TFirst, TEnd                       int64
	EndsAt                             float64
	HasEndsAt                          bool
	Elapsed                            float64
	HasElapsed                         bool
	PlannedMin                         float64
	Total                              int64
	PerHour                            float64
	HasPerHour                         bool
	PSActive                           bool
	PSFills, PSWins, PSReal            int64
	PSNet                              int64
	RegFires, RegFills, RegWins, RegNF int64
	RegTotal                           int64
	Trades, Wins, Losses               int
	StartBal, EstNow                   int64
	HasStartBal, HasEstNow             bool
	Cfg                                []core.CfgItem
	Price                              float64
	NSess                              int
	Err                                string
}

// ListRuns reads dir: every run (newest first by its start, else the files' time), with the running ones marked.
func ListRuns(dir string) ([]RunEntry, error) {
	ents, err := os.ReadDir(dir)
	if err != nil {
		return nil, err
	}
	by := map[string]*RunEntry{}
	for _, e := range ents {
		mm := runFileRX.FindStringSubmatch(e.Name())
		if mm == nil || e.IsDir() {
			continue
		}
		n, _ := strconv.Atoi(mm[2])
		tag := strings.TrimSuffix(strings.TrimSuffix(e.Name(), ".jsonl"), ".log")
		r := by[tag]
		if r == nil {
			reg := "FRA"
			if mm[1] != "" {
				reg = "AMS"
			}
			r = &RunEntry{Tag: tag, Region: reg, N: n, JSONL: core.PyJoin(dir, tag+".jsonl"), Log: core.PyJoin(dir, tag+".log")}
			by[tag] = r
		}
		if info, err := e.Info(); err == nil {
			r.Size += info.Size()
			if info.ModTime().After(r.MTime) {
				r.MTime = info.ModTime()
			}
		}
		if mm[3] == "jsonl" {
			r.HasJ = true
		}
	}
	live := map[string]bool{}
	for _, p := range core.FindEngines() {
		live[p.Log] = true
	}
	out := make([]RunEntry, 0, len(by))
	for _, r := range by {
		r.T0 = firstT(r.JSONL)
		r.Running = live[core.RealPath(r.JSONL)]
		out = append(out, *r)
	}
	sort.SliceStable(out, func(i, j int) bool {
		a, b := out[i], out[j]
		if a.Running != b.Running {
			return a.Running
		}
		ta, tb := a.T0, b.T0
		if ta == 0 {
			ta = a.MTime.UnixNano()
		}
		if tb == 0 {
			tb = b.MTime.UnixNano()
		}
		if ta != tb {
			return ta > tb
		}
		return a.Tag < b.Tag
	})
	return out, nil
}

var firstTCache sync.Map // path -> int64 (a run's start never changes)

// firstT: the run_start record's t (the records' first line), 0 when unknown.
func firstT(path string) int64 {
	if v, ok := firstTCache.Load(path); ok {
		return v.(int64)
	}
	f, err := os.Open(path)
	if err != nil {
		return 0
	}
	defer f.Close()
	br := bufio.NewReaderSize(f, 64<<10)
	line, err := br.ReadSlice('\n')
	if err != nil {
		return 0 // no complete first line yet
	}
	var x struct {
		T  int64  `json:"t"`
		Ev string `json:"ev"`
	}
	if json.Unmarshal(line, &x) != nil || x.T == 0 {
		return 0
	}
	firstTCache.Store(path, x.T)
	return x.T
}

// Summarize computes a run's numbers from a loaded context.
func Summarize(ctx *core.Ctx) *RunSum {
	v := core.BuildView(ctx, -1)
	s := &RunSum{At: time.Now(), Status: v.Status, HowEnded: v.HowEnded, Build: v.Build, TFirst: v.TFirst, TEnd: v.TEnd,
		EndsAt: v.EndsAt, HasEndsAt: v.HasEndsAt, Elapsed: v.Elapsed, HasElapsed: v.HasElapsed, Total: v.Total,
		PerHour: v.PerHour, HasPerHour: v.HasPerHour, PSActive: v.PS.Active, PSFills: v.PS.Fills, PSWins: v.PS.Wins,
		PSReal: v.PS.NReal, PSNet: v.PS.Net, RegFires: v.Reg.Fires, RegFills: v.Reg.Fills, RegWins: v.Reg.Wins,
		RegNF: v.Reg.Guard + v.Reg.Lighthouse + v.Reg.Failed, RegTotal: v.Reg.Total, StartBal: v.RunStartBal,
		HasStartBal: v.HasRunStartBal, EstNow: v.EstNow, HasEstNow: v.HasEstNow, Price: v.Price, NSess: v.NSess}
	if v.Planned.Truthy() {
		s.PlannedMin = v.Planned.Float()
	}
	s.Cfg = append([]core.CfgItem(nil), v.CfgItems...)
	for _, tr := range v.Trades {
		s.Trades++
		if tr.HasPnl && tr.Pnl > 0 {
			s.Wins++
		} else if tr.HasPnl && tr.Pnl < 0 {
			s.Losses++
		}
	}
	return s
}

func newRunCtx(path string, price *core.Price) *core.Ctx {
	src := core.NewSource(path, "", 0, 50)
	eng := core.NewEngine(path, true)
	abs, _ := filepath.Abs(path)
	return &core.Ctx{Src: src, Engine: eng, Price: price, Sys: core.NewSysInfo(filepath.Dir(abs), runtime.NumCPU())}
}

// Explorer is dipview's state; it outlives the dipmon sessions it opens (the selection and the computed numbers stay).
type Explorer struct {
	Dir   string
	Opt   Options
	Price *core.Price
	Duty  float64 // the background loads' duty (like --load-duty)
	Fixed float64 // tests / screenshots: a fixed "now" (s)

	mu     sync.Mutex
	runs   []RunEntry
	sums   map[string]*RunSum
	live   map[string]*core.Ctx // running runs, followed incrementally
	want   string               // the selected run: computed first
	paused bool                 // while dipmon is open
	busy   string               // the run being computed
	worker bool
	sel    string // the selected tag (kept across dipmon sessions)
	usd    bool
	mouse  bool
	scanAt time.Time
	err    string
}

// NewExplorer: the explorer of dir.
func NewExplorer(dir string, o Options, price *core.Price) *Explorer {
	return &Explorer{Dir: dir, Opt: o, Price: price, Duty: 1, sums: map[string]*RunSum{}, live: map[string]*core.Ctx{}, mouse: o.Mouse}
}

// Scan re-reads the directory (every 5 s from the UI).
func (e *Explorer) Scan() {
	runs, err := ListRuns(e.Dir)
	e.mu.Lock()
	defer e.mu.Unlock()
	e.scanAt = time.Now()
	if err != nil {
		e.err = err.Error()
		if os.IsPermission(err) {
			e.err = "cannot read " + e.Dir + " (the run files are root-only: sudo dipview)"
		}
		return
	}
	e.err = ""
	e.runs = runs
	if e.sel == "" && len(runs) > 0 {
		e.sel = runs[0].Tag
	}
}

func runKey(r RunEntry) string { return fmt.Sprintf("%d|%d", r.Size, r.MTime.UnixNano()) }

// next: the run to compute now ("" = nothing to do): the selected run first, then the list in order.
func (e *Explorer) next() (RunEntry, bool) {
	e.mu.Lock()
	defer e.mu.Unlock()
	if e.paused {
		return RunEntry{}, false
	}
	stale := func(r RunEntry) bool {
		if !r.HasJ {
			return false
		}
		s := e.sums[r.Tag]
		if s == nil {
			return true
		}
		if r.Running {
			return time.Since(s.At) > 5*time.Second && (r.Tag == e.want || time.Since(s.At) > 60*time.Second)
		}
		return s.Key != runKey(r)
	}
	for _, r := range e.runs {
		if r.Tag == e.want && stale(r) {
			return r, true
		}
	}
	for _, r := range e.runs {
		if stale(r) {
			return r, true
		}
	}
	return RunEntry{}, false
}

// Compute loads one run (or follows a running one) and stores its numbers.
func (e *Explorer) Compute(r RunEntry) {
	e.mu.Lock()
	ctx := e.live[r.Tag]
	e.busy = r.Tag
	e.mu.Unlock()
	if ctx == nil {
		ctx = newRunCtx(r.JSONL, e.Price)
		ctx.FixedNow = e.Fixed
		ctx.Engine.Scan(true)
		ctx.Src.LoadAll(core.LoadChunk, e.Duty, nil)
	} else {
		ctx.Src.Step(core.TickBytes)
		for ctx.Src.Pending() {
			t0 := time.Now()
			ctx.Src.Step(core.TickBytes)
			time.Sleep(time.Duration(float64(time.Since(t0)) * e.Duty))
		}
		if !ctx.Src.Loaded { // replaced / truncated
			ctx.Src.LoadAll(core.LoadChunk, e.Duty, nil)
		}
	}
	ctx.Src.Loaded = true
	ctx.Engine.Scan(false)
	ctx.Engine.Sample()
	s := Summarize(ctx)
	s.Key = runKey(r)
	e.mu.Lock()
	e.sums[r.Tag] = s
	e.busy = ""
	if r.Running && s.Status != "ENDED" {
		e.live[r.Tag] = ctx
	} else {
		delete(e.live, r.Tag)
	}
	e.mu.Unlock()
}

// ComputeAll computes every run now (tests, --list).
func (e *Explorer) ComputeAll() {
	for {
		r, ok := e.next()
		if !ok {
			return
		}
		e.Compute(r)
	}
}

func (e *Explorer) startWorker() {
	e.mu.Lock()
	if e.worker {
		e.mu.Unlock()
		return
	}
	e.worker = true
	e.mu.Unlock()
	go func() {
		for {
			r, ok := e.next()
			if !ok {
				time.Sleep(time.Second)
				continue
			}
			e.Compute(r)
			time.Sleep(50 * time.Millisecond)
		}
	}()
}

// Runs: the list and the numbers computed so far.
func (e *Explorer) Runs() ([]RunEntry, map[string]*RunSum) {
	e.mu.Lock()
	defer e.mu.Unlock()
	sums := make(map[string]*RunSum, len(e.sums))
	for k, v := range e.sums {
		sums[k] = v
	}
	return append([]RunEntry(nil), e.runs...), sums
}

// ListText: the list as plain text (dipview --list): run, engine, status, start → end, result, fills / wins.
func (e *Explorer) ListText() string {
	runs, sums := e.Runs()
	var b strings.Builder
	for _, r := range runs {
		s := sums[r.Tag]
		st, eng, res, extra := "ended", "?", "?", ""
		if r.Running {
			st = "running"
		}
		if s != nil {
			eng = s.Build
			res = core.SolS(s.Total) + " SOL"
			extra = fmt.Sprintf("  fills %d (%dW)  regular %d buys %d fills  trades %d", s.PSFills, s.PSWins, s.RegFires, s.RegFills, s.Trades)
			if s.Status != "ENDED" {
				st += " (" + s.Status + ")"
			}
		}
		fmt.Fprintf(&b, "%-8s %-6s %-22s %-34s %s%s\n", r.Name(), eng, st, runSpan(r, s, false), res, extra)
	}
	return b.String()
}

// runSpan: "Oct 27 3:26 PM → 5:36 PM" (PKT, 12-hour), "→ now" while running.
func runSpan(r RunEntry, s *RunSum, ascii bool) string {
	t0 := r.T0
	if s != nil && s.TFirst != 0 {
		t0 = s.TFirst
	}
	arrow := " → "
	if ascii {
		arrow = " -> "
	}
	start := "?"
	if t0 != 0 {
		start = strings.Replace(core.T12Date(float64(t0), false), ",", "", 1)
	}
	if r.Running && (s == nil || s.Status == "RUNNING" || s.Status == "STOPPING" || s.Status == "WAITING") {
		return start + arrow + "now"
	}
	var t1 int64
	if s != nil && s.TEnd != 0 {
		t1 = s.TEnd
	} else {
		t1 = r.MTime.UnixNano()
	}
	end := core.T12(float64(t1), false)
	if t0 != 0 && dayOf(t0) != dayOf(t1) {
		end = strings.Replace(core.T12Date(float64(t1), false), ",", "", 1)
	}
	return start + arrow + end
}

// ------------------------------------------------------------------------------------------------- the UI

type exTick struct{}

// exModel is dipview's Bubble Tea model; the REWIND chrome (theme, panels, wordmark) comes from a bare dipmon Model.
type exModel struct {
	e     *Explorer
	c     *Model
	w, h  int
	open  string // the run to open in dipmon (set by Enter, then the program quits)
	top   int
	rowY  int
	lastC time.Time
	lastI int
}

func newExModel(e *Explorer) *exModel {
	c := &Model{opt: e.Opt, dark: true, ascii: e.Opt.ASCII || core.G.ASCII, nowFn: time.Now}
	c.th = NewTheme(true, e.Opt.NoColor)
	return &exModel{e: e, c: c}
}

func (x *exModel) Init() tea.Cmd {
	return tea.Batch(tea.RequestBackgroundColor, x.tick())
}

func (x *exModel) tick() tea.Cmd {
	return tea.Tick(time.Second, func(time.Time) tea.Msg { return exTick{} })
}

func (x *exModel) runs() ([]RunEntry, map[string]*RunSum, int) {
	runs, sums := x.e.Runs()
	x.e.mu.Lock()
	sel := x.e.sel
	x.e.mu.Unlock()
	idx := 0
	for i, r := range runs {
		if r.Tag == sel {
			idx = i
		}
	}
	return runs, sums, idx
}

func (x *exModel) setSel(runs []RunEntry, i int) {
	if len(runs) == 0 {
		return
	}
	i = max(0, min(len(runs)-1, i))
	x.e.mu.Lock()
	x.e.sel = runs[i].Tag
	x.e.want = runs[i].Tag
	x.e.mu.Unlock()
}

func (x *exModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		x.w, x.h = msg.Width, msg.Height
	case tea.BackgroundColorMsg:
		x.c.dark = msg.IsDark()
		x.c.th = NewTheme(x.c.dark, x.e.Opt.NoColor)
	case exTick:
		if time.Since(x.e.scanAt) > 5*time.Second {
			x.e.Scan()
		}
		return x, x.tick()
	case tea.KeyPressMsg:
		runs, _, i := x.runs()
		switch msg.String() {
		case "q", "ctrl+c", "esc":
			return x, tea.Quit
		case "up", "k":
			x.setSel(runs, i-1)
		case "down", "j":
			x.setSel(runs, i+1)
		case "pgup", "b":
			x.setSel(runs, i-max(1, x.h-10))
		case "pgdown", "space":
			x.setSel(runs, i+max(1, x.h-10))
		case "home", "g":
			x.setSel(runs, 0)
		case "end", "G":
			x.setSel(runs, len(runs)-1)
		case "enter", "right", "l":
			if len(runs) > 0 && runs[i].HasJ {
				x.open = runs[i].JSONL
				return x, tea.Quit
			}
		case "u":
			x.e.usd = !x.e.usd
		case "M":
			x.e.mouse = !x.e.mouse
		case "r":
			x.e.Scan()
		}
	case tea.MouseClickMsg:
		mm := msg.Mouse()
		if mm.Button == tea.MouseLeft && x.rowY > 0 && mm.Y >= x.rowY {
			runs, _, _ := x.runs()
			i := x.top + mm.Y - x.rowY
			if i >= 0 && i < len(runs) {
				if i == x.lastI && time.Since(x.lastC) < 500*time.Millisecond && runs[i].HasJ {
					x.open = runs[i].JSONL
					return x, tea.Quit
				}
				x.lastI, x.lastC = i, time.Now()
				x.setSel(runs, i)
			}
		}
	case tea.MouseWheelMsg:
		runs, _, i := x.runs()
		if msg.Mouse().Button == tea.MouseWheelUp {
			x.setSel(runs, i-1)
		} else if msg.Mouse().Button == tea.MouseWheelDown {
			x.setSel(runs, i+1)
		}
	}
	return x, nil
}

func (x *exModel) View() tea.View {
	w, h := x.w, x.h
	if w <= 0 || h <= 0 {
		w, h = 80, 24
	}
	v := tea.NewView(x.render(w, h))
	v.AltScreen = true
	if x.e.mouse {
		v.MouseMode = tea.MouseModeCellMotion
	}
	v.WindowTitle = "REWIND · runs"
	return v
}

func (x *exModel) nowSec() float64 {
	if x.e.Fixed != 0 {
		return x.e.Fixed
	}
	return float64(time.Now().UnixNano()) / 1e9
}

// render draws the explorer at w x h.
func (x *exModel) render(w, h int) string {
	c := x.c
	t := c.th
	if w < 36 || h < 10 {
		return block(t.Warn.Render("terminal too small")+"\n"+t.Lbl.Render(fmt.Sprintf("need 36x10, have %dx%d", w, h)), w, h)
	}
	runs, sums, sel := x.runs()
	x.e.mu.Lock()
	busy, errS := x.e.busy, x.e.err
	x.e.mu.Unlock()
	// header: the wordmark, the directory, the clock and SOL/USD
	price := ""
	if u, _, _, _, _, _ := x.e.Price.Get(); u != 0 {
		price = t.Lbl.Render("SOL ") + t.Val.Render("$"+core.FC(u, 2))
	} else {
		price = t.Lbl.Render("USD n/a")
	}
	sep := t.Dim.Render("  " + c.g("·", "|") + "  ")
	nrun := 0
	for _, r := range runs {
		if r.Running {
			nrun++
		}
	}
	right := t.Val.Render(core.T12(x.nowSec()*1e9, true)) + t.Lbl.Render(" PKT") + sep + price + " "
	label := "run explorer " + c.g("·", "|") + " " + x.e.Dir
	var head string
	if w > 60 && h >= 30 && !c.ascii && !t.Mono {
		head = c.logoBlock(w, 2, false, label, right, false)
	} else {
		head = lr(c.logoLine(2)+"  "+t.Lbl.Render("runs"), right, w)
	}
	hh := lines(head)
	// footer
	keys := "↑/↓ select · enter open in dipmon (q there comes back) · u $/SOL · M mouse · r rescan · q quit"
	if c.ascii {
		keys = "up/down select | enter open in dipmon | u $/SOL | M mouse | r rescan | q quit"
	}
	dsep := c.g(" · ", " | ")
	status := fmt.Sprintf("%d runs%s%d running", len(runs), dsep, nrun)
	if busy != "" {
		status += dsep + "reading " + busy
	}
	foot := lr(" "+t.Key.Render(cut(keys, max(10, w-ansi.StringWidth(status)-4))), t.Lbl.Render(status)+" ", w)
	bh := h - hh - 1
	if errS != "" {
		return head + "\n" + block(" "+t.Bad.Render(errS), w, bh) + "\n" + foot
	}
	// layout: the list left and the overview right; phones: the list, then a short overview
	var body string
	if w >= 90 {
		lw := min(76, max(54, w*48/100))
		rw := w - lw - 1
		list := x.listPanel(runs, sums, sel, lw, bh, hh)
		ov := x.overviewPanel(runs, sums, sel, rw, bh)
		body = hcat(1, list, ov)
	} else {
		oh := min(9, bh/2)
		list := x.listPanel(runs, sums, sel, w, bh-oh, hh)
		ov := x.overviewPanel(runs, sums, sel, w, oh)
		body = list + "\n" + ov
	}
	return head + "\n" + block(body, w, bh) + "\n" + foot
}

// listPanel: one line a run: the dot, the run, the engine, start → end, the result.
func (x *exModel) listPanel(runs []RunEntry, sums map[string]*RunSum, sel, w, h, y0 int) string {
	c := x.c
	t := c.th
	inner := w - 4
	rows := max(1, h-3)
	if sel < x.top {
		x.top = sel
	}
	if sel >= x.top+rows {
		x.top = sel - rows + 1
	}
	x.top = max(0, min(x.top, max(0, len(runs)-rows)))
	x.rowY = y0 + 2
	showEng := inner >= 50
	showRes := inner >= 40
	var ls []string
	hd := padRight("   run", 11)
	if showEng {
		hd += padRight("engine", 7)
	}
	hd += "start " + c.g("→", "->") + " end (PKT)"
	if showRes {
		hd = padRight(hd, inner-10) + padLeft("result", 10)
	}
	ls = append(ls, t.Lbl.Render(cut(hd, inner)))
	if len(runs) == 0 {
		ls = append(ls, t.Lbl.Render("no dip_rN / dip_ams_rN runs in "+x.e.Dir))
	}
	for i := x.top; i < len(runs) && i < x.top+rows; i++ {
		r := runs[i]
		s := sums[r.Tag]
		dot := t.Dim.Render(c.g("●", "."))
		if r.Running {
			dot = t.Good.Render(c.g("●", "+"))
		}
		eng := c.g("…", "~")
		if s != nil && s.Build != "" {
			eng = s.Build
		} else if s != nil {
			eng = "?"
		}
		mark := " "
		if i == sel {
			mark = c.g("▸", ">")
		}
		l := " " + t.Val.Render(padRight(r.Name(), 8))
		if showEng {
			l += t.Lbl.Render(padRight(core.RuneSlice(eng, 6), 7))
		}
		span := runSpan(r, s, c.ascii)
		l += t.Val.Render(span)
		rw := inner - 2
		if showRes {
			res := t.Dim.Render(c.g("…", "~"))
			if s != nil {
				res = t.Money(s.Total, true, false).Render(x.money(s.Total, s.Price))
			} else if !r.HasJ {
				res = t.Dim.Render("log only")
			}
			l = fitLine(l, rw-ansi.StringWidth(res)-1) + " " + res
		}
		l = fitLine(l, rw)
		if i == sel { // the selection: a soft accent bar (the dot keeps its color)
			st := t.Sel.Background(t.SelBg).Bold(true)
			if t.Mono {
				st = st.Reverse(true)
			}
			l = st.Render(mark) + dot + st.Render(ansi.Strip(l))
		} else {
			l = mark + dot + l
		}
		ls = append(ls, l)
	}
	right := ""
	if len(runs) > rows {
		right = t.Acc.Render(fmt.Sprintf("%d/%d", sel+1, len(runs)))
	}
	return c.panel("RUNS", right, strings.Join(ls, "\n"), w, h)
}

func (x *exModel) money(lam int64, price float64) string {
	if x.e.usd && price != 0 {
		return core.Usd(lam, true, price, true, 2)
	}
	return core.SolS(lam)
}

// overviewPanel: the selected run's numbers.
func (x *exModel) overviewPanel(runs []RunEntry, sums map[string]*RunSum, sel, w, h int) string {
	c := x.c
	t := c.th
	if len(runs) == 0 {
		return c.panel("RUN", "", "", w, h)
	}
	r := runs[sel]
	s := sums[r.Tag]
	title := r.Name()
	if s != nil && s.Build != "" {
		title += " " + c.g("·", "|") + " " + s.Build
	}
	var ls []string
	lw := 10
	if s == nil {
		msg := "reading the run " + c.g("…", "...")
		if !r.HasJ {
			msg = "no records file (log only): nothing to show"
		}
		ls = append(ls, t.Lbl.Render(msg), "", c.kv("files", lw, t.Val.Render(fmt.Sprintf("%.1f MB", float64(r.Size)/1e6))+t.Lbl.Render("  "+runSpan(r, nil, c.ascii))))
		return c.panel(title, "", strings.Join(ls, "\n"), w, h)
	}
	st := t.StateDot(StatusState(s.Status), c.ascii) + " " + t.StatusStyle(s.Status).Render(s.Status)
	if r.Running {
		st = t.Good.Render(c.g("●", "+")) + " " + t.StatusStyle(s.Status).Render(s.Status)
	}
	if s.HowEnded != "" {
		st += t.Lbl.Render("  " + s.HowEnded)
	}
	ls = append(ls, st)
	ls = append(ls, c.kv("time", lw, t.Val.Render(runSpan(r, s, c.ascii))+t.Lbl.Render(" PKT")))
	d := c.kv("duration", lw, t.Val.Render(core.Dur(s.Elapsed, s.HasElapsed)))
	if s.PlannedMin > 0 {
		d += t.Lbl.Render(" / " + core.Dur(s.PlannedMin*60, true) + " planned")
	}
	if s.NSess > 1 {
		d += t.Lbl.Render(fmt.Sprintf("  %d sessions", s.NSess))
	}
	ls = append(ls, d)
	ls = append(ls, "")
	// the result in SOL and USD
	res := t.Money(s.Total, true, true).Render(core.SolS(s.Total) + " SOL")
	if s.Price != 0 {
		res += "  " + t.Money(s.Total, true, false).Render(core.Usd(s.Total, true, s.Price, true, 2))
	}
	ls = append(ls, c.kv("result", lw, res))
	if s.HasPerHour {
		ls = append(ls, c.kv("per hour", lw, t.Money(int64(s.PerHour), true, false).Render(x.money(int64(s.PerHour), s.Price)+" /h")))
	}
	sep := t.Dim.Render(" " + c.g("·", "|") + " ")
	ps := t.Lbl.Render("off")
	if s.PSActive {
		ps = t.Money(s.PSNet, true, false).Render(x.money(s.PSNet, s.Price)) + sep + t.Val.Render(fmt.Sprintf("%d fills", s.PSFills)) + sep +
			t.Val.Render(fmt.Sprintf("%d W", s.PSWins))
		if s.PSReal > 0 {
			ps += t.Lbl.Render(fmt.Sprintf(" %.0f%%", float64(s.PSWins)/float64(s.PSReal)*100))
		}
	}
	ls = append(ls, c.kv("pre-send", lw, ps))
	ls = append(ls, c.kv("regular", lw, t.Money(s.RegTotal, true, false).Render(x.money(s.RegTotal, s.Price))+sep+
		t.Val.Render(fmt.Sprintf("%d buys", s.RegFires))+t.Lbl.Render(" "+c.g("→", "->")+" ")+t.Val.Render(fmt.Sprintf("%d fills", s.RegFills))+sep+
		t.Val.Render(fmt.Sprintf("%d failed", s.RegNF))+sep+t.Val.Render(fmt.Sprintf("%d W", s.RegWins))))
	tw := ""
	if s.Trades > 0 {
		tw = t.Lbl.Render(fmt.Sprintf("  win %.0f%%", float64(s.Wins)/float64(s.Trades)*100))
	}
	ls = append(ls, c.kv("trades", lw, t.Val.Render(fmt.Sprintf("%d", s.Trades))+t.Lbl.Render(" · ")+t.Pos.Render(fmt.Sprintf("%d W", s.Wins))+
		t.Lbl.Render(" / ")+t.Neg.Render(fmt.Sprintf("%d L", s.Losses))+tw))
	if s.HasStartBal {
		wl := t.Val.Render(core.F(float64(s.StartBal)/core.LAM, 4))
		if s.HasEstNow {
			wl += t.Lbl.Render(" "+c.g("→", "->")+" ") + t.Val.Render(core.F(float64(s.EstNow)/core.LAM, 4)) + t.Lbl.Render(" SOL (est.)")
		}
		ls = append(ls, c.kv("wallet", lw, wl))
	}
	// the key config, grouped like dipmon's blocks
	ls = append(ls, "", c.subRule("CONFIG", w-4))
	for bi := range cfgBlockKeys {
		var segs []string
		for _, it := range blockItems(s.Cfg, bi) {
			seg := ""
			if it.State != "na" {
				seg = t.StateDot(it.State, c.ascii) + " "
			}
			segs = append(segs, seg+t.Val.Render(it.Short))
		}
		if len(segs) == 0 {
			continue
		}
		ls = append(ls, wrapLines([]string{t.AccB.Render(padRight(cfgBlockShort[bi], lw)) + strings.Join(segs, "  ")}, w-4, lw)...)
	}
	ls = append(ls, "", t.Dim.Render("enter: open in dipmon"+c.g(" · ", " | ")+"USD at today's SOL price"))
	return c.panel(title, "", strings.Join(ls, "\n"), w, h)
}

// ExplorerScreen renders the explorer once at w x h (tests, screenshots); the numbers must be computed (ComputeAll).
func ExplorerScreen(e *Explorer, w, h int, keepANSI bool) string {
	x := newExModel(e)
	x.w, x.h = w, h
	return plain(x.render(w, h), keepANSI)
}

// Explore runs the explorer until the owner opens a run (its records path) or quits ("").
func Explore(e *Explorer) string {
	e.mu.Lock()
	e.paused = false
	e.mu.Unlock()
	e.Scan()
	e.mu.Lock()
	e.want = e.sel
	e.mu.Unlock()
	e.startWorker()
	if e.Price != nil {
		e.Price.OnChange = nil
	}
	x := newExModel(e)
	opts := []tea.ProgramOption{tea.WithFPS(15)}
	p := tea.NewProgram(x, opts...)
	if _, err := p.Run(); err != nil {
		fmt.Fprintln(os.Stderr, "dipview:", err)
		return ""
	}
	e.mu.Lock()
	if x.open != "" {
		e.paused = true // dipmon reads the run itself; the background loads wait
	}
	e.mu.Unlock()
	return x.open
}

// dayOf: the PKT calendar day of t (ns).
func dayOf(t int64) string {
	d := core.PyTime(float64(t))
	return d.Format("2006-01-02")
}
