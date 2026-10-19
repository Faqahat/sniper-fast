# PRE-CREATE signal test

Sample: 1535 launches joined with pre-create features. Population (unbiased feed) = 1140 (883 with a post-create price series -> defined pump outcome); his picks (sniper 4yFAz) = 395.

Outcomes: pump15 = max price reached >=1.5x entry; pump20 >=2.0x. netR = net return fraction per snipe under the winner exit (derisk .30 ride 2.0 trail .85 cut .80 ladder .40 cap 20); opt fills = 8%% slip / .0008 SOL-leg / entry@floor; real fills = 12%% slip / .005 SOL-leg / entry 5%% above floor.

Pre-create features are measured strictly from creator wallet history BEFORE the create slot (funding inflow, prior activity), so they are knowable at/just before the create.

## Baseline (all population w/ series)
  pump15=34.9% pump20=15.4% netR_opt=+0.0301 netR_real=-0.0696  n=883

## A. Pre-create feature -> pump outcome (unbiased population)

### CREATOR FUNDING RECENCY (slots before create; 150 slots~=1min)  [FULL]
  band                       n    p15%    p20%  netR_opt netR_real
  fresh <1min(<150)        263   34.2%   12.5%   -0.0441   -0.1374
  1-5min(150-750)          229   29.3%   12.7%   -0.0108   -0.1065
  5-30min(750-4500)        170   41.2%   17.6%   +0.1109   +0.0035
  30min-2h(4500-18k)        74   44.6%   20.3%   +0.2003   +0.0850
  >2h(>=18k)                67   31.3%   20.9%   +0.1609   +0.0494

  [OOS train(slot<456742465) vs val]
  fresh <1min(<150)       train p15= 32.7% (n 171)   val p15= 37.0% (n  92)
  1-5min(150-750)         train p15= 29.4% (n 160)   val p15= 29.0% (n  69)
  5-30min(750-4500)       train p15= 43.6% (n 117)   val p15= 35.8% (n  53)
  30min-2h(4500-18k)      train p15= 40.4% (n  47)   val p15= 51.9% (n  27)
  >2h(>=18k)              train p15= 37.5% (n  48)   val p15= 15.8% (n  19)

### CREATOR FUNDING AMOUNT (SOL of last inflow)  [FULL]
  band                       n    p15%    p20%  netR_opt netR_real
  <0.5 SOL                 444   32.2%   13.1%   -0.0629   -0.1539
  0.5-1                    105   32.4%   15.2%   +0.0065   -0.0916
  1-2                      129   33.3%   12.4%   +0.0954   -0.0111
  2-5                       82   42.7%   17.1%   +0.1981   +0.0824
  >=5                       43   60.5%   39.5%   +0.6760   +0.5188

  [OOS train(slot<456742465) vs val]
  <0.5 SOL                train p15= 33.5% (n 313)   val p15= 29.0% (n 131)
  0.5-1                   train p15= 32.9% (n  70)   val p15= 31.4% (n  35)
  1-2                     train p15= 32.5% (n  77)   val p15= 34.6% (n  52)
  2-5                     train p15= 39.6% (n  53)   val p15= 48.3% (n  29)
  >=5                     train p15= 56.7% (n  30)   val p15= 69.2% (n  13)

### SHARED-FUNDER FANOUT (# distinct creators the funding source funded)  [FULL]
  band                       n    p15%    p20%  netR_opt netR_real
  solo src(1)              728   34.8%   15.1%   +0.0006   -0.0964
  shared 2                  38   21.1%    0.0%   -0.0513   -0.1439
  shared 3-4                13   46.2%   23.1%   +0.1613   +0.0500
  shared >=5               104   39.4%   22.1%   +0.2503   +0.1302

  [OOS train(slot<456742465) vs val]
  solo src(1)             train p15= 35.0% (n 494)   val p15= 34.2% (n 234)
  shared 2                train p15= 19.2% (n  26)   val p15= 25.0% (n  12)
  shared 3-4              train p15= 50.0% (n  12)   val p15=  0.0% (n   1)
  shared >=5              train p15= 42.1% (n  76)   val p15= 32.1% (n  28)

### CREATOR PRE-ACTIVITY (prior tx count in window)  [FULL]
  band                       n    p15%    p20%  netR_opt netR_real
  cold <=2 tx              182   37.4%   20.3%   +0.1803   +0.0673
  3-20                      99   27.3%   17.2%   +0.1004   -0.0057
  21-200                   212   32.1%    9.9%   -0.0550   -0.1469
  >200                     390   37.2%   15.6%   -0.0115   -0.1077

  [OOS train(slot<456742465) vs val]
  cold <=2 tx             train p15= 41.7% (n 132)   val p15= 26.0% (n  50)
  3-20                    train p15= 28.6% (n  70)   val p15= 24.1% (n  29)
  21-200                  train p15= 33.3% (n 153)   val p15= 28.8% (n  59)
  >200                    train p15= 35.6% (n 253)   val p15= 40.1% (n 137)

### SERIAL LAUNCHER (# launches by creator in window)  [FULL]
  band                       n    p15%    p20%  netR_opt netR_real
  1 launch                 408   31.9%   16.9%   +0.0983   -0.0073
  2                        108   40.7%   13.9%   -0.0159   -0.1116
  3-5                      129   30.2%   10.1%   +0.0026   -0.0950
  >5                       238   39.9%   16.4%   -0.0509   -0.1436

  [OOS train(slot<456742465) vs val]
  1 launch                train p15= 34.2% (n 281)   val p15= 26.8% (n 127)
  2                       train p15= 41.3% (n  75)   val p15= 39.4% (n  33)
  3-5                     train p15= 33.7% (n  92)   val p15= 21.6% (n  37)
  >5                      train p15= 36.2% (n 160)   val p15= 47.4% (n  78)

### MARKET DENSITY (pop creates in preceding 300 slots)  [FULL]
  band                       n    p15%    p20%  netR_opt netR_real
  quiet <=1                530   36.2%   15.5%   +0.0399   -0.0607
  2-3                      352   33.0%   15.3%   +0.0156   -0.0829
  4-6                        1    0.0%    0.0%   -0.0269   -0.1199
  >6 hot                     0    0.0%    0.0%   +0.0000   +0.0000

  [OOS train(slot<456742465) vs val]
  quiet <=1               train p15= 38.4% (n 310)   val p15= 33.2% (n 220)
  2-3                     train p15= 32.7% (n 297)   val p15= 34.5% (n  55)
  4-6                     train p15=  0.0% (n   1)   val p15=  0.0% (n   0)
  >6 hot                  train p15=  0.0% (n   0)   val p15=  0.0% (n   0)

## B. Same, restricted to VANILLA snipeable population (n=374) -- what we'd actually buy

### CREATOR FUNDING RECENCY (slots before create; 150 slots~=1min)  [VANILLA pop]
  band                       n    p15%    p20%  netR_opt netR_real
  fresh <1min(<150)         36   11.1%    5.6%   -0.0256   -0.1206
  1-5min(150-750)           97   19.6%   10.3%   +0.0638   -0.0391
  5-30min(750-4500)         99   40.4%   19.2%   +0.1973   +0.0820
  30min-2h(4500-18k)        45   42.2%   20.0%   +0.2886   +0.1654
  >2h(>=18k)                44   34.1%   25.0%   +0.2463   +0.1276

### SHARED-FUNDER FANOUT (# distinct creators the funding source funded)  [VANILLA pop]
  band                       n    p15%    p20%  netR_opt netR_real
  solo src(1)              269   27.9%   15.2%   +0.0779   -0.0260
  shared 2                  18   16.7%    0.0%   -0.0656   -0.1568
  shared 3-4                12   41.7%   25.0%   +0.1827   +0.0694
  shared >=5                75   40.0%   24.0%   +0.3327   +0.2052

### SERIAL LAUNCHER (# launches by creator in window)  [VANILLA pop]
  band                       n    p15%    p20%  netR_opt netR_real
  1 launch                 289   31.8%   18.3%   +0.1530   +0.0424
  2                         29   37.9%   20.7%   -0.0047   -0.1017
  3-5                       36   16.7%    5.6%   +0.0579   -0.0456
  >5                        20   20.0%    5.0%   +0.0379   -0.0637

## C. His-picks vs population separation (is pre-create setup part of his selection?)

  fund_recency_slots   POP med=    567.00 mean=  12824.66  |  HIS med=   2751.00 mean=  24705.94
  fund_amount          POP med=      0.33 mean=      4.12  |  HIS med=      1.29 mean=      2.77
  src_fanout           POP med=      1.00 mean=      6.35  |  HIS med=      1.00 mean=      8.76
  prior_n              POP med=    119.00 mean=    227.15  |  HIS med=      2.00 mean=     90.09
  serial_launches      POP med=      1.00 mean=      6.42  |  HIS med=      1.00 mean=      1.94
  density              POP med=      1.00 mean=      1.37  |  HIS med=      0.00 mean=      0.37

  fresh-funded(<1min)   POP=28.6%  HIS=1.7%
  shared-funder(>=3)    POP=15.3%  HIS=18.5%
  serial(>1 launch)     POP=49.9%  HIS=33.2%
  cold creator(<=2 tx)  POP=19.2%  HIS=52.9%

## D. Coverage & knowability
  create anchor found 92.8%, funding inflow found 85.0% of launches.
