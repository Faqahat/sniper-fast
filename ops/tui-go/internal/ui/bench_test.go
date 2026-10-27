package ui

import (
	"os"
	"testing"

	"dipmon/internal/core"
)

func benchCtx(b testing.TB, path string) *core.Ctx {
	if _, err := os.Stat(path); err != nil {
		b.Skip("no data")
	}
	src := core.NewSource(path, "", 0, 3000)
	src.LoadAll(core.LoadChunk, 0, nil)
	eng := core.NewEngine(path, false)
	return &core.Ctx{Src: src, Engine: eng, Price: core.NewPrice(187.42, false), Sys: core.NewSysInfo("/", 2), FixedNow: 1793104617.2}
}

func BenchmarkRender200x35(b *testing.B) {
	ctx := benchCtx(b, "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r27.jsonl")
	m := screenModel(ctx, Options{Sound: "all", Version: "t"}, 200, 35)
	m.screenMode = false
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = m.render(200, 35)
	}
}

func BenchmarkBuildView(b *testing.B) {
	ctx := benchCtx(b, "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r24.jsonl")
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		_ = core.BuildView(ctx, -1)
	}
}

func BenchmarkRender80x24Uncached(b *testing.B) {
	ctx := benchCtx(b, "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r26.jsonl")
	m := screenModel(ctx, Options{Sound: "all", Version: "t"}, 80, 24)
	m.screenMode = false
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		m.bodyK = "" // a live second: the body changes
		m.rebuild()
		_ = m.render(80, 24)
	}
}
