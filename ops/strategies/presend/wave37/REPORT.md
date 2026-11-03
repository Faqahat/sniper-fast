# WAVE sell vs live 200 ms timer — AMS run 37 (10-29, PKT)

Code: wave37.py (copy of sniper-omen3/w1_wave_real.py; paths, `time-ms` exit name, TP20/SL50 wave variant, dump size added), an37.py.
Data: /home/moiz/sniper-data/wave37 (tape `tab/` from local recorder chunks 10-29 07:25 -> 16:11 PKT, last chunk partial; r37 records copied 16:16 PKT; wave37.json per fill; an37.out).

- Coverage: ALL 138 r37 fills (07:32 -> 15:56 PKT), size 0.687 SOL on curve. Live realized +3.05 SOL (+22.1 mSOL/fill).
- Timer leg check: model vs real curve sell, mean abs error 0.0000005 mSOL (max 0.000001). Exact.
- Wave (TP10/SL20) − timer: all followers −2.32 mSOL/fill (90% CI −7.8..+2.5), total −0.32 SOL; −20% followers −0.93 (−5.0..+2.8), −0.13 SOL.
  Better 34 / worse 25 / same 79.
- Wave with the live TP20/SL50 (timing only): −0.04 mSOL/fill (−5.1..+4.5), −0.005 SOL; −20%: −0.07, −0.01 SOL. Better 35 / worse 18 / same 85.
  So the timing alone is a wash; the extra loss of the standard wave comes from its tighter TP10 (cuts winners).
- Worst: 51Gp1r99 −236 (07:51), 2qRwR3Rp −226 (11:08), A9gLrKQo −136, Cm13WrXd −61, 6igVWiQR −53 mSOL.
  Best: DeZHhE8c +123 (live TP), Atjp5Had +90, FGk5XL9t +89, AskKxScm +44, 777EpMee +41. Links https://gmgn.ai/sol/token/<mint>.
- By hour (wave−timer, mSOL/fill): 07 −35.7 (9), 08 +6.2, 09 +3.8, 10 −2.4, 11 −10.9, 12 +6.5, 13 +5.3, 14 −5.9, 15 −0.3. Noisy, driven by 3 big swings.
- By dump size: 1–2 SOL +5.1 (4), 2–4 SOL −2.1 (69), ≥4 SOL −3.0 (65; −0.4 with TP20/SL50).
- vs r35 (−3.4 mSOL/fill, 0.65 SOL, 49 fills): r37 −2.3 at 0.69 SOL, 138 fills. Same sign, CIs overlap zero; sizes almost equal, so no sign that size makes the wave worse.
- Verdict: no gain from the wave on r37; keep the 200 ms timer.
