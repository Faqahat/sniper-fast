package ui

import (
	"fmt"
	"math"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	"charm.land/bubbles/v2/help"
	"charm.land/bubbles/v2/spinner"
	"charm.land/bubbles/v2/textinput"
	"charm.land/bubbles/v2/viewport"
	tea "charm.land/bubbletea/v2"
	"charm.land/lipgloss/v2"
	"github.com/charmbracelet/colorprofile"
	"github.com/charmbracelet/harmonica"
	"github.com/charmbracelet/x/ansi"

	"dipmon/internal/core"
)

// Options: the UI's command-line settings.
type Options struct {
	Interval, LoadDuty                     float64
	NoColor, ASCII, Notify, NoAnim, Strict bool
	Sound, Version                         string
	BellLog                                string // tests: one line per bell
	Golden                                 bool   // tests: fixed probe values (system, pid, clock) for golden screens
}

var tabNames = []string{"Overview", "Pre-send", "Regular", "Trades", "Health", "Log", "Config"}
var tabShort = []string{"Ovw", "PS", "Reg", "Trd", "Hlth", "Log", "Cfg"}
var filters = []string{"all", "pre-send", "regular", "wins", "losses", "open"}

const (
	animFPS   = 15 // the renderer's frame cap and the animation rate (each renderer tick costs a wakeup, so idle CPU scales with it)
	animSpan  = 2 * time.Second
	bellGap   = 2 * time.Second
	bigTrade  = 30_000_000 // |P&L| >= 0.03 SOL: a "big" trade (sound mode big, --notify)
	loadChunk = core.LoadChunk
)

// messages
type (
	loadMsg  struct{}
	dataMsg  struct{ gen int }
	frameMsg struct{}
	bellMsg  struct{}
	priceMsg struct{}
	todayMsg struct{}
	spinTick struct{}
)

// rowHL: a trade row's highlight (when its P&L became final).
type rowHL struct {
	at  time.Time
	pnl int64
}

// Model is the Bubble Tea model.
type Model struct {
	ctx  *core.Ctx
	opt  Options
	th   *Theme
	dark bool

	ascii bool
	w, h  int

	// data
	view        *core.View
	loading     bool
	loadTotal   int64
	loadStarted time.Time
	loadedAt    time.Time
	evSeen      int64
	paused      bool
	interval    float64
	scope       int
	dataGen     int
	today       *core.Today
	todayOn     bool
	todayCard   core.Card
	runSer      *core.PnLSeries // the run's P&L a minute (the chart, the ATH / low)
	todaySer    *core.PnLSeries // the day's (with s)
	armFrame    int

	// ui
	tab        int
	showHelp   bool
	detail     *core.Trade
	scroll     map[string]int
	maxScroll  int
	moreHint   string
	tradeSel   int
	tradeTop   int
	tradeRows  []*core.Trade
	tfilter    int
	searching  bool
	query      string
	search     textinput.Model
	logAll     bool
	logWrap    bool
	logOff     int
	usdFirst   bool
	anim       bool
	sound      string
	muted      bool
	keys       keyMap
	helpM      help.Model
	spin       spinner.Model
	vp         viewport.Model
	tabX       [][2]int
	tabY       int
	bodyY      int
	tradeRowY  int
	uiErrs     int
	uiErr      string
	screenMode bool
	cfgCols    int

	// animation
	spring     harmonica.Spring
	heroPos    float64
	heroVel    float64
	heroTarget float64
	heroInit   bool
	flashAt    time.Time
	toastAmt   int64
	toastAt    time.Time
	hl         map[int]rowHL
	pulseAt    time.Time
	lastAnim   time.Time
	ticking    bool
	priceSpin  bool
	prevTotal  int64

	// bell
	lastBell    time.Time
	bellPending int
	bellArmed   bool
	bellCovered int
	bellLog     *os.File
	bells       int

	// caches
	chartKey string
	chartOut string
	cfgCache map[string]cfgCached
	trKey    string
	trOut    string
	bodyK    string
	bodyOut  string
	bodyHint string
	barCache map[string]string
	latKey   string
	latSum   *core.LatSummary
	mu       sync.Mutex
	nowFn    func() time.Time
}

// New builds the model for a context whose source may still need its initial load.
func New(ctx *core.Ctx, o Options) *Model {
	m := &Model{ctx: ctx, opt: o, dark: true, ascii: o.ASCII || core.G.ASCII, interval: clampF(o.Interval, 0.5, 5),
		scope: -1, scroll: map[string]int{}, anim: !o.NoAnim, sound: o.Sound, hl: map[int]rowHL{}, cfgCache: map[string]cfgCached{}, barCache: map[string]string{},
		keys: newKeyMap(), helpM: help.New(), nowFn: time.Now}
	if m.sound == "" {
		m.sound = "all"
	}
	m.th = NewTheme(true, o.NoColor)
	m.applyTheme()
	m.spin = spinner.New(spinner.WithSpinner(spinner.MiniDot))
	m.search = textinput.New()
	m.search.Placeholder = "mint prefix"
	m.search.Prompt = "/ "
	m.search.CharLimit = 44
	m.vp = viewport.New()
	m.spring = harmonica.NewSpring(harmonica.FPS(animFPS), 7.0, 1.0)
	m.today = core.NewToday(ctx.Src)
	if o.BellLog != "" {
		if f, err := os.Create(o.BellLog); err == nil {
			m.bellLog = f
		}
	}
	return m
}

func clampF(x, lo, hi float64) float64 { return math.Max(lo, math.Min(hi, x)) }

func (m *Model) applyTheme() {
	t := m.th
	hs := help.DefaultStyles(m.dark)
	hs.ShortKey = t.Key
	hs.ShortDesc = t.KeyDesc
	hs.ShortSeparator = t.Dim
	hs.FullKey = t.Key
	hs.FullDesc = t.KeyDesc
	hs.FullSeparator = t.Dim
	hs.Ellipsis = t.Dim
	m.helpM.Styles = hs
	m.spin.Style = t.Acc
	if m.ascii {
		m.helpM.ShortSeparator = " | "
		m.helpM.FullSeparator = "   "
		m.helpM.Ellipsis = "~"
	} else {
		m.helpM.ShortSeparator = " · "
	}
}

// now is the wall clock (overridable in tests).
func (m *Model) now() time.Time { return m.nowFn() }

// ------------------------------------------------------------------------------------------------- tea.Model

// Init starts the initial load (chunked, the CPU yielded between chunks) and asks for the background color.
func (m *Model) Init() tea.Cmd {
	cmds := []tea.Cmd{tea.RequestBackgroundColor}
	if !m.ctx.Src.Loaded {
		m.loading = true
		m.loadStarted = m.now()
		m.loadTotal = max(1, m.ctx.Src.TotalBytes())
		cmds = append(cmds, func() tea.Msg { return loadMsg{} }, m.spin.Tick)
	} else {
		m.afterLoad()
		cmds = append(cmds, m.dataTick(m.interval))
	}
	return tea.Batch(cmds...)
}

func (m *Model) dataTick(sec float64) tea.Cmd {
	m.dataGen++
	g := m.dataGen
	return tea.Tick(time.Duration(sec*float64(time.Second)), func(time.Time) tea.Msg { return dataMsg{gen: g} })
}

func (m *Model) frameTick() tea.Cmd {
	return tea.Tick(time.Second/animFPS, func(time.Time) tea.Msg { return frameMsg{} })
}

// afterLoad: the load is done; numbers become live, trades loaded so far never ring.
func (m *Model) afterLoad() {
	src := m.ctx.Src
	src.Loaded = true
	m.loading = false
	m.loadedAt = m.now()
	m.ctx.Engine.Sample()
	m.ctx.Sys.Sample(true)
	m.rebuild()
	m.evSeen = src.Model.EventSeq
	m.prevTotal = m.view.Total
	if m.bellLog != nil {
		fmt.Fprintf(m.bellLog, "# loaded %.3f %d\n", float64(m.now().UnixNano())/1e9, src.Model.EventSeq)
		_ = m.bellLog.Sync()
	}
	m.heroPos, m.heroTarget, m.heroInit = float64(m.view.Total)/core.LAM, float64(m.view.Total)/core.LAM, true
}

func (m *Model) rebuild() {
	m.view = core.BuildView(m.ctx, m.scope)
	m.runSer = m.view.PnL()
	if m.todayOn {
		m.refreshToday()
	}
}

// refreshToday: the day card and the day's P&L series (its last point is the card's net).
func (m *Model) refreshToday() {
	m.todayCard = m.today.Total(m.ctx.Src.Model)
	if m.view != nil {
		m.todaySer = m.today.Series(m.ctx.Src.Model, m.view.NowNS(), m.todayCard.Net)
	}
}

// pnl is the P&L series of the scope the card shows (this run, or today with s): the chart, the ATH and the low.
func (m *Model) pnl() *core.PnLSeries {
	if m.todayOn {
		return m.todaySer
	}
	return m.runSer
}

// Update handles every message.
func (m *Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.w, m.h = msg.Width, msg.Height
		m.helpM.SetWidth(msg.Width)
		return m, nil
	case tea.BackgroundColorMsg:
		m.dark = msg.IsDark()
		m.th = NewTheme(m.dark, m.opt.NoColor)
		m.applyTheme()
		m.chartKey, m.trKey = "", ""
		m.cfgCache = map[string]cfgCached{}
		m.barCache = map[string]string{}
		return m, nil
	case loadMsg:
		return m, m.loadStep()
	case spinner.TickMsg:
		if !m.loading && !m.priceSpin {
			return m, nil
		}
		var cmd tea.Cmd
		m.spin, cmd = m.spin.Update(msg)
		return m, cmd
	case dataMsg:
		if msg.gen != m.dataGen {
			return m, nil
		}
		return m, m.onData()
	case frameMsg:
		return m, m.onFrame()
	case bellMsg:
		return m, m.flushBell()
	case priceMsg:
		m.priceSpin = false
		if !m.loading {
			m.rebuild()
		}
		return m, nil
	case tea.KeyPressMsg:
		return m, m.onKey(msg)
	case tea.MouseClickMsg:
		return m, m.onClick(msg.Mouse())
	case tea.MouseWheelMsg:
		mm := msg.Mouse()
		switch mm.Button {
		case tea.MouseWheelUp:
			m.scrollBy(-3)
		case tea.MouseWheelDown:
			m.scrollBy(3)
		}
		return m, nil
	case tea.PasteMsg:
		if m.searching {
			var cmd tea.Cmd
			m.search, cmd = m.search.Update(msg)
			m.query = m.search.Value()
			return m, cmd
		}
	}
	return m, nil
}

// loadStep reads one chunk and schedules the next after a pause proportional to the work (duty).
func (m *Model) loadStep() tea.Cmd {
	src := m.ctx.Src
	t0 := m.now()
	n := src.Step(loadChunk)
	work := m.now().Sub(t0)
	m.loadTotal = max(m.loadTotal, src.DoneBytes()+src.TJ.Pending()+src.TL.Pending())
	if n == 0 && !src.Pending() {
		m.afterLoad()
		return tea.Batch(m.dataTick(m.interval), m.stopSpinCmd())
	}
	d := time.Duration(float64(work) * m.opt.LoadDuty)
	if d < 2*time.Millisecond {
		d = 2 * time.Millisecond
	}
	return tea.Tick(d, func(time.Time) tea.Msg { return loadMsg{} })
}

func (m *Model) stopSpinCmd() tea.Cmd { return nil }

// onData: read what the engine wrote, sample the probes, rebuild the numbers, react to new closed trades.
func (m *Model) onData() tea.Cmd {
	src := m.ctx.Src
	src.Step(core.TickBytes)
	if !src.Loaded { // the files were truncated / replaced: reload from the start
		m.loading = true
		m.loadStarted = m.now()
		m.loadTotal = max(1, src.TotalBytes())
		m.evSeen = 0
		return tea.Batch(func() tea.Msg { return loadMsg{} }, m.spin.Tick)
	}
	m.ctx.Engine.Sample()
	m.ctx.Sys.Sample(false)
	todayWork := time.Duration(0)
	if m.todayOn && m.today.Pending() > 0 {
		t0 := m.now()
		m.today.Step(core.LoadChunk) // the same chunks as the initial load: the same booking minutes
		todayWork = m.now().Sub(t0)
	}
	if m.todayOn && m.view != nil && m.today.Started() { // a new PKT day: rescan the runs directory
		if m0, _, _ := core.DayRange(m.view.NowNS()); m0 != m.today.Day.From {
			m.today.Start(m.view.NowNS())
		}
	}
	m.armFrame++
	var cmds []tea.Cmd
	if !m.paused {
		m.rebuild()
		if c := m.onEvents(); c != nil {
			cmds = append(cmds, c)
		}
	} else {
		m.drainBellOnly(&cmds)
	}
	next := m.interval
	if src.Pending() {
		next = 0.05
	} else if m.todayOn && m.today.Pending() > 0 {
		next = math.Max(0.05, todayWork.Seconds()*math.Max(1, m.opt.LoadDuty)) // the other runs load gently
	}
	cmds = append(cmds, m.dataTick(next))
	return tea.Batch(cmds...)
}

// onEvents: trades whose P&L became final since the last look: highlight, toast, chart pulse, hero spring, bell.
func (m *Model) onEvents() tea.Cmd {
	M := m.ctx.Src.Model
	var cmds []tea.Cmd
	if M.EventSeq > m.evSeen {
		now := m.now()
		var sum int64
		var ring []core.Event
		for _, ev := range M.Events {
			if ev.Seq <= m.evSeen {
				continue
			}
			sum += ev.Pnl
			m.hl[ev.Trade.ID] = rowHL{at: now, pnl: ev.Pnl}
			ring = append(ring, ev)
		}
		m.evSeen = M.EventSeq
		if len(ring) > 0 {
			if m.anim {
				m.toastAmt, m.toastAt, m.flashAt, m.pulseAt, m.lastAnim = sum, now, now, now, now
			}
			if c := m.bellFor(ring); c != nil {
				cmds = append(cmds, c)
			}
		}
	}
	if m.view != nil {
		// the hero rolls (a Harmonica spring) only when trades close; other changes (fees of failed tries every few
		// seconds) snap, so the frame loop runs only around real events and idle CPU stays tiny
		target := float64(m.view.Total) / core.LAM
		if target != m.heroTarget {
			m.heroTarget = target
			if !m.anim || m.lastAnim.IsZero() || m.now().Sub(m.lastAnim) >= animSpan {
				m.heroPos, m.heroVel = target, 0
			}
		}
	}
	if m.anim && !m.ticking && m.now().Sub(m.lastAnim) < animSpan {
		m.ticking = true
		cmds = append(cmds, m.frameTick())
	}
	if len(cmds) == 0 {
		return nil
	}
	return tea.Batch(cmds...)
}

// drainBellOnly: while paused the screen stays frozen, but closed trades still ring.
func (m *Model) drainBellOnly(cmds *[]tea.Cmd) {
	M := m.ctx.Src.Model
	if M.EventSeq <= m.evSeen {
		return
	}
	var ring []core.Event
	for _, ev := range M.Events {
		if ev.Seq > m.evSeen {
			ring = append(ring, ev)
		}
	}
	m.evSeen = M.EventSeq
	if c := m.bellFor(ring); c != nil {
		*cmds = append(*cmds, c)
	}
}

// onFrame advances the animations (~30 fps) and stops ticking once they are done.
func (m *Model) onFrame() tea.Cmd {
	now := m.now()
	if !m.anim {
		m.ticking = false
		return nil
	}
	m.heroPos, m.heroVel = m.spring.Update(m.heroPos, m.heroVel, m.heroTarget)
	settled := math.Abs(m.heroPos-m.heroTarget) < 5e-6 && math.Abs(m.heroVel) < 5e-5
	if settled {
		m.heroPos, m.heroVel = m.heroTarget, 0
	}
	if now.Sub(m.lastAnim) < animSpan || !settled || m.priceSpin {
		return m.frameTick()
	}
	m.ticking = false
	for id, h := range m.hl {
		if now.Sub(h.at) > animSpan {
			delete(m.hl, id)
		}
	}
	return nil
}

// ------------------------------------------------------------------------------------------------- the bell

func (m *Model) wantsBell(ev core.Event) bool {
	if m.muted {
		return false
	}
	switch m.sound {
	case "off":
		return false
	case "wins":
		return ev.Pnl > 0
	case "big":
		return ev.Pnl >= bigTrade || ev.Pnl <= -bigTrade
	}
	return true
}

// bellFor rings once for new closed trades, at most once per 2 s (a burst is merged into one bell).
func (m *Model) bellFor(evs []core.Event) tea.Cmd {
	n := 0
	var notes []string
	for _, ev := range evs {
		if m.wantsBell(ev) {
			n++
		}
		if m.opt.Notify && (ev.Pnl >= bigTrade || ev.Pnl <= -bigTrade) && !m.muted && m.sound != "off" {
			notes = append(notes, fmt.Sprintf("REWIND %s %s %s SOL", kindTag(ev.Trade), core.Short(ev.Trade.Mint, 6), core.SolS(ev.Pnl)))
		}
	}
	var cmds []tea.Cmd
	for _, s := range notes {
		cmds = append(cmds, tea.Raw(ansi.Notify(s)))
	}
	if n > 0 {
		now := m.now()
		if now.Sub(m.lastBell) >= bellGap && !m.bellArmed {
			cmds = append(cmds, m.ring(now, n))
		} else {
			m.bellPending += n
			if !m.bellArmed {
				m.bellArmed = true
				wait := bellGap - now.Sub(m.lastBell)
				cmds = append(cmds, tea.Tick(wait, func(time.Time) tea.Msg { return bellMsg{} }))
			}
		}
	}
	if len(cmds) == 0 {
		return nil
	}
	return tea.Batch(cmds...)
}

func (m *Model) flushBell() tea.Cmd {
	m.bellArmed = false
	if m.bellPending == 0 {
		return nil
	}
	n := m.bellPending
	m.bellPending = 0
	if m.muted || m.sound == "off" {
		return nil
	}
	return m.ring(m.now(), n)
}

func (m *Model) ring(now time.Time, covered int) tea.Cmd {
	m.lastBell = now
	m.bells++
	if m.bellLog != nil {
		fmt.Fprintf(m.bellLog, "%.3f %d\n", float64(now.UnixNano())/1e9, covered)
		_ = m.bellLog.Sync()
	}
	return tea.Raw("\a")
}

func kindTag(tr *core.Trade) string {
	if tr.Kind == "PS" {
		return "PS"
	}
	return "REG"
}

// ------------------------------------------------------------------------------------------------- keys

func (m *Model) onKey(msg tea.KeyPressMsg) tea.Cmd {
	k := msg.String()
	if m.searching {
		switch k {
		case "esc":
			m.searching = false
			m.query = ""
			m.search.SetValue("")
			m.search.Blur()
			return nil
		case "enter":
			m.searching = false
			m.search.Blur()
			m.tradeSel, m.tradeTop = 0, 0
			return nil
		case "ctrl+c":
			return tea.Quit
		}
		var cmd tea.Cmd
		m.search, cmd = m.search.Update(msg)
		m.query = m.search.Value()
		m.tradeSel, m.tradeTop = 0, 0
		return cmd
	}
	if k == "q" || k == "ctrl+c" {
		return tea.Quit
	}
	if m.showHelp {
		m.showHelp = false
		return nil
	}
	if m.loading {
		return nil
	}
	switch k {
	case "?":
		m.showHelp = true
		m.scroll["help"] = 0
	case "esc":
		m.detail = nil
		if m.query != "" && m.tab == 3 {
			m.query = ""
			m.search.SetValue("")
		}
	case "1", "2", "3", "4", "5", "6", "7":
		m.tab = int(k[0] - '1')
		m.detail = nil
	case "tab":
		m.tab = (m.tab + 1) % len(tabNames)
		m.detail = nil
	case "shift+tab":
		m.tab = (m.tab + len(tabNames) - 1) % len(tabNames)
		m.detail = nil
	case "u":
		m.usdFirst = !m.usdFirst
	case "p":
		m.paused = !m.paused
		if !m.paused {
			m.rebuild()
		}
	case "r":
		if m.ctx.Price != nil && m.ctx.Price.Net {
			m.ctx.Price.Refresh()
			m.priceSpin = true
			return tea.Batch(m.spin.Tick, tea.Tick(6*time.Second, func(time.Time) tea.Msg { return priceMsg{} }))
		}
	case "+", "=":
		steps := []float64{0.5, 1, 2, 3, 5}
		nv := 0.5
		for _, s := range steps {
			if s < m.interval {
				nv = s
			}
		}
		m.interval = nv
		return m.dataTick(m.interval)
	case "-", "_":
		steps := []float64{0.5, 1, 2, 3, 5}
		nv := 5.0
		for i := len(steps) - 1; i >= 0; i-- {
			if steps[i] > m.interval {
				nv = steps[i]
			}
		}
		m.interval = nv
		return m.dataTick(m.interval)
	case "s":
		m.todayOn = !m.todayOn
		if m.todayOn {
			if !m.today.Started() && m.view != nil {
				m.today.Start(m.view.NowNS())
			}
			m.refreshToday()
			return m.dataTick(0.05)
		}
	case "S":
		n := len(m.ctx.Src.Model.Sessions)
		if n > 1 {
			if m.scope < 0 {
				m.scope = 0
			} else if m.scope+1 >= n {
				m.scope = -1
			} else {
				m.scope++
			}
			m.rebuild()
		}
	case "a":
		m.anim = !m.anim
		if !m.anim {
			m.heroPos, m.heroVel = m.heroTarget, 0
			m.hl = map[int]rowHL{}
		}
	case "m":
		m.muted = !m.muted
	case "f", "i":
		if m.tab == 3 && m.detail == nil {
			m.tfilter = (m.tfilter + 1) % len(filters)
			m.tradeSel, m.tradeTop = 0, 0
		} else if m.tab == 5 {
			m.logAll = !m.logAll
			m.logOff = 0
		}
	case "/":
		if m.tab == 3 && m.detail == nil {
			m.searching = true
			m.search.SetValue(m.query)
			return m.search.Focus()
		}
	case "w":
		if m.tab == 5 {
			m.logWrap = !m.logWrap
		}
	case "enter":
		if m.tab == 3 && m.detail == nil && len(m.tradeRows) > 0 {
			m.detail = m.tradeRows[min(m.tradeSel, len(m.tradeRows)-1)]
			m.scroll["detail"] = 0
		}
	default:
		m.scrollKey(k)
	}
	return nil
}

func (m *Model) page() int { return max(1, m.h-8) }

func (m *Model) scrollKey(k string) {
	d := 0
	home, end := false, false
	switch k {
	case "up", "k":
		d = -1
	case "down", "j":
		d = 1
	case "pgup", "b":
		d = -m.page()
	case "pgdown", "space":
		d = m.page()
	case "home", "g":
		home = true
	case "end", "G":
		end = true
	default:
		return
	}
	switch {
	case m.showHelp:
	case m.tab == 3 && m.detail == nil:
		n := len(m.tradeRows)
		switch {
		case home:
			m.tradeSel = 0
		case end:
			m.tradeSel = max(0, n-1)
		default:
			m.tradeSel = max(0, min(n-1, m.tradeSel+d))
		}
	case m.tab == 5 && m.detail == nil:
		switch {
		case home:
			m.logOff = 1 << 30
		case end:
			m.logOff = 0
		default:
			m.logOff = max(0, m.logOff-d)
		}
	default:
		key := m.scrollKeyName()
		cur := m.scroll[key]
		switch {
		case home:
			m.scroll[key] = 0
		case end:
			m.scroll[key] = 1 << 30
		default:
			m.scroll[key] = max(0, cur+d)
		}
	}
}

func (m *Model) scrollBy(d int) {
	switch {
	case m.tab == 3 && m.detail == nil && !m.showHelp:
		n := len(m.tradeRows)
		m.tradeSel = max(0, min(n-1, m.tradeSel+d))
	case m.tab == 5 && m.detail == nil && !m.showHelp:
		m.logOff = max(0, m.logOff-d)
	default:
		key := m.scrollKeyName()
		m.scroll[key] = max(0, m.scroll[key]+d)
	}
}

func (m *Model) scrollKeyName() string {
	switch {
	case m.showHelp:
		return "help"
	case m.detail != nil:
		return "detail"
	}
	return fmt.Sprintf("tab%d", m.tab)
}

func (m *Model) onClick(mm tea.Mouse) tea.Cmd {
	if mm.Button != tea.MouseLeft || m.loading {
		return nil
	}
	if m.showHelp {
		m.showHelp = false
		return nil
	}
	if mm.Y == m.tabY {
		for i, r := range m.tabX {
			if mm.X >= r[0] && mm.X < r[1] {
				m.tab = i
				m.detail = nil
				return nil
			}
		}
	}
	if m.tab == 3 && m.detail == nil && m.tradeRowY > 0 && mm.Y >= m.tradeRowY {
		i := m.tradeTop + (mm.Y - m.tradeRowY)
		if i >= 0 && i < len(m.tradeRows) {
			if i == m.tradeSel {
				m.detail = m.tradeRows[i]
				m.scroll["detail"] = 0
			} else {
				m.tradeSel = i
			}
		}
	}
	return nil
}

// ------------------------------------------------------------------------------------------------- view

// View renders the frame.
func (m *Model) View() tea.View {
	w, h := m.w, m.h
	if w <= 0 || h <= 0 {
		w, h = 80, 24
	}
	content := m.safeRender(w, h)
	v := tea.NewView(content)
	v.AltScreen = true
	v.MouseMode = tea.MouseModeCellMotion
	v.WindowTitle = m.windowTitle()
	// no native progress bar (OSC 9;4): older iTerm2 builds show OSC 9 as a desktop notification
	return v
}

func (m *Model) windowTitle() string {
	v := m.view
	if v == nil {
		return "REWIND"
	}
	run := "?"
	if v.HasRun {
		run = fmt.Sprintf("%s r%d", v.Region, v.Run)
	}
	return fmt.Sprintf("REWIND · %s · %s SOL", run, core.SolS(v.Total))
}

func (m *Model) loadFrac() float64 {
	if m.loadTotal <= 0 {
		return 0
	}
	return math.Min(1, float64(m.ctx.Src.DoneBytes())/float64(m.loadTotal))
}

func (m *Model) safeRender(w, h int) (out string) {
	if !m.opt.Strict {
		defer func() {
			if r := recover(); r != nil {
				m.uiErrs++
				m.uiErr = fmt.Sprint(r)
				out = block("UI ERROR "+m.uiErr, w, h)
			}
		}()
	}
	return m.render(w, h)
}

// render draws the whole frame at w x h.
func (m *Model) render(w, h int) string {
	if w < 36 || h < 10 {
		return block(m.th.Warn.Render("terminal too small")+"\n"+m.th.Lbl.Render(fmt.Sprintf("need 36x10, have %dx%d", w, h)), w, h)
	}
	if m.loading || m.view == nil {
		if m.ascii {
			return asciiFold(m.splash(w, h))
		}
		return m.splash(w, h)
	}
	head := m.header(w, h)
	hh := lines(head)
	tabs := m.tabBar(w)
	m.tabY = hh
	foot := m.footer(w)
	bh := h - hh - 1 - lines(foot)
	m.bodyY = hh + 1
	body := m.body(w, bh)
	frame := head + "\n" + tabs + "\n" + body + "\n" + foot
	if m.showHelp {
		frame = m.overlayHelp(frame, w, h)
	}
	if m.ascii {
		frame = asciiFold(frame)
	}
	return frame
}

// bodyKey captures everything the body depends on; "" = do not cache (an animation is running).
func (m *Model) bodyKey(w, bh int) string {
	if m.anim && (m.now().Sub(m.lastAnim) < animSpan || m.now().Sub(m.toastAt) < animSpan || m.now().Sub(m.pulseAt) < animSpan) {
		return ""
	}
	if m.priceSpin || m.searching {
		return ""
	}
	v := m.view
	now := m.nowSec()
	tick := int64(now / 60)
	if m.tab == 4 || (v.Running && ((v.HasSElapsed && v.SElapsed < 120) || (v.Quiet.HasOnAt && float64(v.Quiet.OnAt)/1e9-now < 120))) {
		tick = int64(now)
	}
	arm := 0
	if v.Running && v.PSOpenNow > 0 {
		arm = m.armFrame
	}
	det := 0
	if m.detail != nil {
		det = m.detail.ID
	}
	M := m.ctx.Src.Model
	return fmt.Sprintf("%d|%d|%d|%d|%s|%d|%d|%d|%d|%d|%d|%s|%v|%v|%d|%v|%v|%d|%v|%d|%v|%v|%g|%s|%d|%d|%d|%d|%d",
		w, bh, M.Version, M.TradeVer, v.Status, tick, arm, m.tab, det, m.tradeSel, m.tradeTop, m.query, m.logAll, m.logWrap, m.logOff,
		m.usdFirst, m.todayOn, m.todayCard.Net+int64(m.todayCard.Loading)*7919+serKey(m.pnl()), m.dark, m.scope, m.ascii, m.anim, v.Price,
		fmt.Sprint(m.scroll[m.scrollKeyName()]), m.tfilter, v.PSOpenNow, len(m.hl), m.todayCard.Buys, int64(v.PriceAge/60))
}

// serKey changes when a series gains a minute or its last point moves.
func serKey(s *core.PnLSeries) int64 {
	if !s.Ok() {
		return 0
	}
	return int64(len(s.Vals))*1000003 + s.End()*31 + s.M0
}

// body renders the current tab (scrolling tabs are sliced by their offset); cached while nothing it shows changed.
func (m *Model) body(w, bh int) string {
	if bh < 1 {
		return ""
	}
	key := m.bodyKey(w, bh)
	if key != "" && key == m.bodyK {
		m.moreHint = m.bodyHint
		return m.bodyOut
	}
	out := m.bodyRaw(w, bh)
	m.bodyK, m.bodyOut, m.bodyHint = key, out, m.moreHint
	return out
}

func (m *Model) bodyRaw(w, bh int) string {
	var s string
	scrolls := true
	m.moreHint = ""
	switch {
	case m.detail != nil:
		s = m.scrDetail(w, bh, m.detail)
	default:
		switch m.tab {
		case 0:
			s, scrolls = m.scrOverview(w, bh), false
		case 1:
			s = m.scrPresend(w, bh)
		case 2:
			s = m.scrRegular(w, bh)
		case 3:
			s, scrolls = m.scrTrades(w, bh), false
		case 4:
			s = m.scrHealth(w, bh)
		case 5:
			s, scrolls = m.scrLog(w, bh), false
		default:
			s = m.scrConfig(w, bh)
		}
	}
	if !scrolls {
		return block(s, w, bh)
	}
	ls := strings.Split(s, "\n")
	key := m.scrollKeyName()
	off := m.scroll[key]
	m.maxScroll = max(0, len(ls)-bh)
	off = max(0, min(off, m.maxScroll))
	m.scroll[key] = off
	if len(ls) > bh {
		left := len(ls) - bh - off
		if left > 0 {
			m.moreHint = fmt.Sprintf("%s %d more", m.g("▼", "v"), left)
		} else {
			m.moreHint = m.g("▲ home", "^ home")
		}
		ls = ls[off : off+bh]
	}
	return block(strings.Join(ls, "\n"), w, bh)
}

// g picks the Unicode or the ASCII form.
func (m *Model) g(uni, asc string) string {
	if m.ascii {
		return asc
	}
	return uni
}

// ------------------------------------------------------------------------------------------------- chrome

// header: the REWIND wordmark (full / compact / one line by the terminal's size) with the run's label and status.
func (m *Model) header(w, h int) string {
	t := m.th
	v := m.view
	label := "pump.fun dip bot"
	if v.HasRun {
		label = strings.ToLower(v.Region) + " · run " + fmt.Sprint(v.Run)
		if m.ascii {
			label = strings.ToLower(v.Region) + " | run " + fmt.Sprint(v.Run)
		}
	}
	label += " " + m.g("·", "|") + " " + v.Build
	dot := t.StateDot(StatusState(v.Status), m.ascii)
	st := t.StatusStyle(v.Status).Render(v.Status)
	clock := core.T12(float64(m.now().UnixNano()), true)
	if m.ctx.FixedNow != 0 {
		clock = core.T12(m.ctx.FixedNow*1e9, true)
	}
	price := ""
	if v.Price != 0 {
		price = t.Lbl.Render("SOL ") + t.Val.Render("$"+core.FC(v.Price, 2))
		if m.priceSpin {
			price += " " + m.spin.View()
		} else if v.PriceAgeOK {
			price += t.Dim.Render(" " + core.AgeS(v.PriceAge, true))
		}
	} else {
		price = t.Lbl.Render("USD n/a")
	}
	sep := t.Dim.Render("  " + m.g("·", "|") + "  ")
	right := dot + " " + st + sep + t.Val.Render(clock) + t.Lbl.Render(" PKT") + sep + price
	if m.paused {
		right = t.Warn.Bold(true).Render("PAUSED") + sep + right
	}
	compactable := w > 60 && h >= 30 && !m.ascii && !t.Mono
	switch {
	case compactable && h >= 40 && w >= 100:
		return m.logoBlock(w, 3, false, label, right+" ", false)
	case compactable:
		return m.logoBlock(w, 2, false, label, right+" ", false)
	}
	// one line: the wordmark, the run, the status, the run P&L
	left := m.logoLine(2) + "  " + dot + " " + t.Lbl.Render(m.runTag())
	pnl := t.Money(v.Total, true, true).Render(core.SolS(v.Total) + " SOL")
	r := pnl
	if w >= 70 {
		r = st + sep + pnl
		if v.Price != 0 {
			r += t.Dim.Render("  " + core.Usd(v.Total, true, v.Price, true, 2))
		}
	}
	return lr(left, r+" ", w)
}

func (m *Model) runTag() string {
	v := m.view
	if v.HasRun {
		return fmt.Sprintf("%s r%d", v.Region, v.Run)
	}
	return core.RuneSlice(m.ctx.Src.JSONL, 20)
}

// tabBar: the tabs with the active one in a soft accent pill; mouse clicks switch tabs.
func (m *Model) tabBar(w int) string {
	t := m.th
	names := tabNames
	if w < 100 {
		names = tabShort
	}
	var b strings.Builder
	x := 0
	m.tabX = m.tabX[:0]
	b.WriteString(" ")
	x++
	for i, n := range names {
		label := fmt.Sprintf(" %d %s ", i+1, n)
		if w < 56 && i != m.tab {
			label = fmt.Sprintf(" %d ", i+1)
		}
		lw := ansi.StringWidth(label)
		st := t.TabOff
		if i == m.tab && m.detail == nil {
			st = t.TabOn
		} else if i == m.tab {
			st = t.Acc
		}
		b.WriteString(st.Render(label))
		m.tabX = append(m.tabX, [2]int{x, x + lw})
		x += lw
		if i < len(names)-1 {
			b.WriteString(" ")
			x++
		}
	}
	right := ""
	v := m.view
	if v != nil && v.NSess > 1 {
		if v.Scope < 0 {
			right = t.Acc.Render("all sessions")
		} else {
			right = t.Acc.Render(fmt.Sprintf("session %d/%d", v.Scope+1, v.NSess))
		}
	}
	if m.todayOn {
		if right != "" {
			right += t.Dim.Render(" · ")
		}
		right += t.Acc.Render("today")
	}
	if ansi.StringWidth(b.String())+ansi.StringWidth(right)+2 > w {
		right = ""
	}
	return lr(b.String(), right+" ", w)
}

// footer: the alerts strip and the help bar (generated from the key map) with the sound / rate indicators.
func (m *Model) footer(w int) string {
	t := m.th
	v := m.view
	// alerts
	var al string
	if len(v.Alerts) == 0 {
		al = t.Good.Render(m.g("✓ ", "ok ")) + t.Lbl.Render("all clear")
	} else {
		var parts []string
		used := 0
		shown := 0
		for _, a := range v.Alerts {
			sym, st := m.g("▲", "^"), t.Warn
			switch a.Level {
			case "bad":
				st = t.Bad
			case "end":
				sym, st = m.g("◆", "+"), t.Acc
			}
			text := a.Text
			if a.Level == "end" {
				text = to12End(text, v)
			}
			seg := st.Render(sym + " " + text)
			sw := ansi.StringWidth(seg)
			if shown > 0 && used+3+sw > w-6 {
				break
			}
			parts = append(parts, seg)
			used += sw + 3
			shown++
		}
		al = strings.Join(parts, "   ")
		if shown < len(v.Alerts) {
			al += t.Lbl.Render(fmt.Sprintf("  +%d", len(v.Alerts)-shown))
		}
	}
	al = " " + cut(al, w-2)
	// help bar
	m.keys.tab, m.keys.detail = m.tab, m.detail != nil
	m.helpM.SetWidth(max(10, w-26))
	hb := m.helpM.ShortHelpView(m.keys.ShortHelp())
	snd := "♪ " + m.sound
	if m.muted || m.sound == "off" {
		snd = m.g("♪ off", "- off")
		if m.muted {
			snd = "- muted"
		}
	}
	if m.ascii && !(m.muted || m.sound == "off") {
		snd = "~ " + m.sound
	}
	rate := core.G0(m.interval) + "s"
	ri := ""
	if m.moreHint != "" {
		ri += t.Acc.Render(m.moreHint) + "  "
	}
	if !m.anim && !m.screenMode {
		ri += t.Dim.Render("anim off") + "  "
	}
	ri += t.Lbl.Render(snd + "  " + rate)
	return fitLine(al, w) + "\n" + lr(" "+hb, ri+" ", w)
}

// to12End rewrites the end banner's 24-hour time to 12-hour form.
func to12End(text string, v *core.View) string {
	hhmm := core.Clock(float64(v.TEnd), "%H:%M")
	if v.TEnd != 0 && strings.Contains(text, "RUN ENDED "+hhmm) {
		return strings.Replace(text, "RUN ENDED "+hhmm, "RUN ENDED "+core.T12(float64(v.TEnd), false), 1)
	}
	return text
}

// overlayHelp composites the help panel over the frame (Lip Gloss layers).
func (m *Model) overlayHelp(frame string, w, h int) string {
	hw := min(w-4, 96)
	hh := min(h-4, 34)
	body := m.helpContent(hw - 4)
	ls := strings.Split(body, "\n")
	off := m.scroll["help"]
	maxOff := max(0, len(ls)-(hh-2))
	off = max(0, min(off, maxOff))
	m.scroll["help"] = off
	right := m.th.Dim.Render("dipmon " + m.opt.Version)
	if len(ls) > hh-2 {
		more := ""
		if off > 0 {
			more += m.g("↑", "^")
		}
		if off < maxOff {
			more += m.g("↓", "v")
		}
		right = m.th.Acc.Render(more+" scroll") + m.th.Dim.Render("  dipmon "+m.opt.Version)
		ls = ls[off:min(len(ls), off+hh-2)]
	}
	box := m.panel("REWIND · help", right, strings.Join(ls, "\n"), hw, hh)
	x := max(0, (w-hw)/2)
	y := max(0, (h-hh)/2)
	base := lipgloss.NewLayer(frame)
	top := lipgloss.NewLayer(box).X(x).Y(y).Z(1)
	return lipgloss.NewCompositor(base, top).Render()
}

// ------------------------------------------------------------------------------------------------- run

// Run starts the program and returns the exit code (1 after UI errors).
func Run(ctx *core.Ctx, o Options) int {
	m := New(ctx, o)
	fps := animFPS
	if x, err := strconv.Atoi(os.Getenv("DIPMON_FPS")); err == nil && x > 0 { // diagnostics
		fps = x
	}
	opts := []tea.ProgramOption{tea.WithFPS(fps)}
	if o.NoColor {
		opts = append(opts, tea.WithColorProfile(colorprofile.ASCII)) // attributes (bold / faint / reverse) only
	}
	if o.Strict {
		opts = append(opts, tea.WithoutCatchPanics())
	}
	p := tea.NewProgram(m, opts...)
	if ctx.Price != nil {
		ctx.Price.OnChange = func() { p.Send(priceMsg{}) }
	}
	if _, err := p.Run(); err != nil {
		fmt.Fprintln(os.Stderr, "dipmon:", err)
		return 1
	}
	if m.bellLog != nil {
		fmt.Fprintf(m.bellLog, "# exit %.3f %d\n", float64(time.Now().UnixNano())/1e9, ctx.Src.Model.EventSeq)
		m.bellLog.Close()
	}
	if m.uiErrs > 0 {
		fmt.Fprintf(os.Stderr, "dipmon: %d UI error(s); last: %s\n", m.uiErrs, m.uiErr)
		return 1
	}
	return 0
}
