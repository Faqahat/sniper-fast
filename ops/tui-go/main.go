// dipmon v3 (REWIND): a read-only live terminal monitor for one pump.fun dip-bot run (the engine's <TAG>.jsonl +
// <TAG>.log), built on Bubble Tea / Lip Gloss / Bubbles / Harmonica / ntcharts. Its accounting is the Python
// dipmon v1's (= the standard run reports), to the lamport; --snapshot --json prints the same fields.
//
//	sudo dipmon                 the running engine's run (its --dip-log), else the newest run file in /root/prod/runs
//	sudo dipmon --run 27        /root/prod/runs/dip_ams_r27.* (--region ams|fra when both exist)
//	sudo dipmon --snapshot      a plain-text summary (--json: machine-readable, lamports), then exit
//	dipmon --file X.jsonl       any run file (finished runs, local copies); the .log next to it is read too
//	dipmon --screen 200x35      render the UI once as plain text (screenshots), then exit
package main

import (
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"runtime/pprof"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"time"

	"dipmon/internal/core"
	"dipmon/internal/ui"
)

const version = "3.0"

const defaultDir = "/root/prod/runs"

type floatFlag struct {
	v   float64
	set bool
}

func (f *floatFlag) String() string { return strconv.FormatFloat(f.v, 'g', -1, 64) }
func (f *floatFlag) Set(s string) error {
	v, err := strconv.ParseFloat(s, 64)
	if err != nil {
		return err
	}
	f.v, f.set = v, true
	return nil
}

type intFlag struct {
	v   int
	set bool
}

func (f *intFlag) String() string { return strconv.Itoa(f.v) }
func (f *intFlag) Set(s string) error {
	v, err := strconv.Atoi(s)
	if err != nil {
		return err
	}
	f.v, f.set = v, true
	return nil
}

func die(format string, a ...any) {
	fmt.Fprintf(os.Stderr, "dipmon: "+format+"\n", a...)
	os.Exit(1)
}

// renice: nice 19 and the idle I/O class for every thread of the process (Linux nice / ioprio are per thread; threads
// started later inherit them), so dipmon never competes with the live engine even without the wrapper.
func renice() {
	const ioprioWhoProcess, ioprioClassIdle, ioprioSetSyscall = 1, 3, 251 // x86_64
	tids := []int{0}
	if ents, err := os.ReadDir("/proc/self/task"); err == nil {
		tids = tids[:0]
		for _, e := range ents {
			if n, err := strconv.Atoi(e.Name()); err == nil {
				tids = append(tids, n)
			}
		}
	}
	for _, tid := range tids {
		if p, err := syscall.Getpriority(syscall.PRIO_PROCESS, tid); err == nil && 20-p < 19 {
			_ = syscall.Setpriority(syscall.PRIO_PROCESS, tid, 19)
		}
		if runtime.GOARCH == "amd64" {
			_, _, _ = syscall.Syscall(ioprioSetSyscall, ioprioWhoProcess, uintptr(tid), ioprioClassIdle<<13)
		}
	}
}

func findRun(file, dir, region string, run intFlag) string {
	if file != "" {
		return file
	}
	if run.set {
		var cands []string
		regs := []string{"ams", "fra"}
		if region != "" {
			regs = []string{region}
		}
		for _, rg := range regs {
			tag := "dip_r" + strconv.Itoa(run.v)
			if rg == "ams" {
				tag = "dip_ams_r" + strconv.Itoa(run.v)
			}
			p := core.PyJoin(dir, tag+".jsonl")
			_, e1 := os.Stat(p)
			_, e2 := os.Stat(strings.TrimSuffix(p, ".jsonl") + ".log")
			if e1 == nil || e2 == nil {
				cands = append(cands, p)
			}
		}
		if len(cands) == 1 {
			return cands[0]
		}
		if len(cands) > 1 {
			die("both dip_ams_r%d and dip_r%d are in %s: pass --region ams|fra", run.v, run.v, dir)
		}
		if f, err := os.Open(dir); err != nil {
			die("cannot read %s (the run files are root-only: sudo dipmon ...)", dir)
		} else {
			f.Close()
		}
		die("no run %d in %s", run.v, dir)
	}
	if eng := core.FindEngines(); len(eng) > 0 {
		sort.SliceStable(eng, func(i, j int) bool { return mtime(eng[i].Log) > mtime(eng[j].Log) })
		return eng[0].Log
	}
	ents, err := os.ReadDir(dir)
	if err != nil {
		if os.IsPermission(err) {
			die("cannot read %s (the run files are root-only: sudo dipmon ...)", dir)
		}
		die("no %s here; pass --dir DIR, --file X.jsonl or --run N", dir)
	}
	best, bestT := "", -1.0
	for _, e := range ents {
		if _, _, ok := core.RunInfo(e.Name()); !ok {
			continue
		}
		p := core.PyJoin(dir, e.Name())
		if t := mtime(p); t > bestT {
			best, bestT = p, t
		}
	}
	if best == "" {
		die("no running engine and no dip_*rN.jsonl in %s", dir)
	}
	return best
}

func mtime(p string) float64 {
	st, err := os.Stat(p)
	if err != nil {
		return 0
	}
	return float64(st.ModTime().UnixNano()) / 1e9
}

func parseSize(s string) (int, int, bool) {
	w, h, ok := strings.Cut(strings.ToLower(strings.TrimSpace(s)), "x")
	if !ok {
		return 0, 0, false
	}
	wi, e1 := strconv.Atoi(w)
	hi, e2 := strconv.Atoi(h)
	if e1 != nil || e2 != nil || wi <= 0 || hi <= 0 {
		return 0, 0, false
	}
	return wi, hi, true
}

func main() {
	fs := flag.NewFlagSet("dipmon", flag.ExitOnError)
	fs.Usage = func() {
		fmt.Fprintf(os.Stderr, "usage: dipmon [options]\n\nREWIND (dipmon %s): read-only live monitor for a dip-bot run (the engine's .jsonl + .log)\n\noptions:\n", version)
		fs.VisitAll(func(f *flag.Flag) {
			if f.Usage == "" {
				return // test / diagnostic flags
			}
			name, usage := flag.UnquoteUsage(f)
			arg := "--" + f.Name
			if name != "" {
				arg += " " + strings.ToUpper(name)
			}
			def := ""
			if f.DefValue != "" && f.DefValue != "false" && f.DefValue != "0" {
				def = " (default " + f.DefValue + ")"
			}
			fmt.Fprintf(os.Stderr, "  %-22s %s%s\n", arg, usage, def)
		})
	}
	file := fs.String("file", "", "a run's records (X.jsonl); its .log is read from next to it")
	logp := fs.String("log", "", "the text log (default: the .jsonl's name with .log)")
	var run intFlag
	fs.Var(&run, "run", "run number N: <dir>/dip_ams_rN or dip_rN")
	region := fs.String("region", "", "with --run: ams | fra")
	dir := fs.String("dir", defaultDir, "run files directory")
	budget := fs.String("budget", "", "the dip budget file (default: <dir>/../dip_budget_ams.json or dip_budget.json)")
	snapshot := fs.Bool("snapshot", false, "print a plain-text summary and exit (no UI)")
	jsonOut := fs.Bool("json", false, "with --snapshot: JSON instead of text (lamports)")
	var usd floatFlag
	fs.Var(&usd, "usd", "fixed SOL/USD price (no network)")
	noUSD := fs.Bool("no-usd", false, "no price fetch (SOL only unless cached)")
	ascii := fs.Bool("ascii", false, "ASCII only (no Unicode glyphs)")
	noColor := fs.Bool("no-color", false, "monochrome")
	interval := fs.Float64("interval", 1.0, "refresh seconds, 0.5-5")
	loadDuty := fs.Float64("load-duty", 1.0, "initial load: sleep this many times each chunk's work time (1 = at most ~50% of a core)")
	sound := fs.String("sound", "all", "terminal bell on closed trades: all | wins | big (|P&L| >= 0.03 SOL) | off")
	notify := fs.Bool("notify", false, "also send a desktop notification (OSC 9) for big trades")
	noAnim := fs.Bool("no-anim", false, "no animations (a toggles them)")
	screen := fs.String("screen", "", "render the UI once at WxH as plain text to stdout, then exit (--tab, --page)")
	tab := fs.Int("tab", 1, "with --screen: the tab 1-7")
	page := fs.String("page", "", "with --screen: help | detail | splash | today")
	screens := fs.String("screens", "", "write text screenshots of every tab to DIR and exit")
	sizes := fs.String("sizes", "200x35,160x50,120x40,80x24,50x30", "with --screens: WxH list")
	screensTag := fs.String("screens-tag", "", "")
	screensColor := fs.Bool("screens-ansi", false, "with --screen(s): keep the colors (ANSI)")
	var nowF floatFlag
	fs.Var(&nowF, "now", "")
	assume := fs.Bool("assume-running", false, "")
	strict := fs.Bool("strict", false, "")
	exitJSON := fs.String("exit-json", "", "")
	extra := fs.Bool("extra", false, "with --snapshot --json: add the v3 figures (trading card, today)")
	golden := fs.Bool("golden", false, "")
	cpuprof := fs.String("cpuprofile", "", "")
	bellLog := fs.String("bell-log", "", "")
	showVersion := fs.Bool("version", false, "print the version")
	_ = fs.Parse(os.Args[1:])
	if *showVersion {
		fmt.Println("dipmon " + version)
		return
	}
	if *region != "" && *region != "ams" && *region != "fra" {
		fmt.Fprintln(os.Stderr, "dipmon: argument --region: invalid choice: '"+*region+"' (choose from 'ams', 'fra')")
		os.Exit(2)
	}
	switch *sound {
	case "all", "wins", "big", "off":
	default:
		fmt.Fprintln(os.Stderr, "dipmon: argument --sound: invalid choice: '"+*sound+"' (choose from 'all', 'wins', 'big', 'off')")
		os.Exit(2)
	}
	renice()
	if t := os.Getenv("TERM"); t == "" || t == "dumb" || t == "unknown" {
		_ = os.Setenv("TERM", "xterm-256color")
	}
	core.SetASCII(*ascii)

	path := findRun(*file, *dir, *region, run)
	eng := core.NewEngine(path, true)
	eng.Scan(true)
	var fee int64
	if eng.Alive() {
		e := eng.Snapshot()
		a, e1 := strconv.ParseInt(e.Flags["--cu-limit"], 10, 64)
		b, e2 := strconv.ParseInt(e.Flags["--cu-price-micro"], 10, 64)
		if e1 == nil && e2 == nil {
			fee = 5_000 + a*b/1_000_000
		}
	}
	src := core.NewSource(path, *logp, fee, 3000)
	reg := strings.ToLower(src.Region)
	bpath := *budget
	if bpath == "" {
		abs, _ := filepath.Abs(path)
		name := "dip_budget.json"
		if reg == "ams" {
			name = "dip_budget_ams.json"
		}
		bpath = core.PyJoin(filepath.Dir(abs), "..", name)
	}
	if _, err := os.Stat(bpath); err != nil {
		bpath = ""
	}
	price := core.NewPrice(usd.v, !*noUSD)
	abs, _ := filepath.Abs(path)
	sysi := core.NewSysInfo(filepath.Dir(abs), runtime.NumCPU())
	ctx := &core.Ctx{Src: src, Engine: eng, Price: price, Sys: sysi, BudgetPath: bpath, AssumeRunning: *assume}
	if nowF.set {
		ctx.FixedNow = nowF.v
	}
	if !src.Exists() {
		die("%s not found", src.JSONL)
	}
	opts := ui.Options{Interval: *interval, LoadDuty: *loadDuty, NoColor: *noColor, ASCII: *ascii, Sound: *sound, Notify: *notify,
		NoAnim: *noAnim, Strict: *strict, Version: version, Golden: *golden, BellLog: *bellLog}

	if *snapshot || *screens != "" || *screen != "" {
		duty := *loadDuty
		if *screens != "" || *screen != "" {
			duty = 0
		}
		src.LoadAll(core.LoadChunk, duty, nil)
		eng.Sample()
		if eng.Alive() {
			time.Sleep(250 * time.Millisecond)
			eng.Sample()
		}
		sysi.Sample(true)
		if price.Net && func() bool { u, _, _, _, _, _ := price.Get(); return u == 0 }() && *screens == "" && *screen == "" {
			price.FetchOnce(4 * time.Second)
		}
		if *screens != "" {
			var sz [][2]int
			for _, x := range strings.Split(*sizes, ",") {
				w, h, ok := parseSize(x)
				if !ok {
					die("bad size %q", x)
				}
				sz = append(sz, [2]int{w, h})
			}
			files, err := ui.DumpScreens(ctx, opts, *screens, sz, *screensTag, *screensColor)
			if err != nil {
				die("%v", err)
			}
			for _, f := range files {
				fmt.Println(f)
			}
			return
		}
		if *screen != "" {
			w, h, ok := parseSize(*screen)
			if !ok {
				die("bad --screen %q (WxH)", *screen)
			}
			fmt.Print(ui.RenderScreen(ctx, opts, w, h, *tab-1, *page, *screensColor))
			return
		}
		v := core.BuildView(ctx, -1)
		if *jsonOut {
			var ex *core.JObj
			if *extra {
				ex = ui.ExtraJSON(ctx, v)
			}
			fmt.Println(core.SnapshotJSON(v, ctx, ex))
		} else {
			fmt.Println(core.SnapshotText(v, ctx, 110))
		}
		return
	}
	price.Start()
	if *cpuprof != "" { // diagnostics: profile from 8 s after the start (after the initial load) to the exit
		go func() {
			time.Sleep(8 * time.Second)
			if f, err := os.Create(*cpuprof); err == nil {
				_ = pprof.StartCPUProfile(f)
			}
		}()
	}
	code := ui.Run(ctx, opts)
	if *exitJSON != "" {
		v := core.BuildView(ctx, -1)
		_ = os.WriteFile(*exitJSON, []byte(core.SnapshotJSON(v, ctx, ui.ExtraJSON(ctx, v))), 0o644)
	}
	if *cpuprof != "" {
		pprof.StopCPUProfile()
	}
	os.Exit(code)
}
