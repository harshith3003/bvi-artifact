# Item 2: threshold robustness (selftest)

Splits: 50; bootstrap: 300; seed 20260909.

## amr122 (operating threshold 0.412)

| Attack | AUC | EER | FAR at theta [95% CI] |
|---|---|---|---|
| full_asv | 1.0000 | 0.00% | 0.00% [0.00-0.00] |
| pause_3 | 1.0000 | 0.00% | 0.00% [0.00-0.00] |
| splice_0.5 | 0.4689 | 55.05% | 95.83% [92.06-99.17] |
| splice_1 | 0.4708 | 52.36% | 96.67% [93.33-99.17] |
| splice_3 | 0.9737 | 6.67% | 22.50% [15.83-29.60] |

FRR at theta: 1.02% [0.46-1.67] over 120 calls x conditions.

Threshold over 50 speaker-disjoint splits: mean 0.410, sd 0.004, 95% range 0.404-0.419; test FRR mean 1.27% (95% range 0.00-2.41%).

## amr122_g711u (operating threshold 0.402)

| Attack | AUC | EER | FAR at theta [95% CI] |
|---|---|---|---|
| full_asv | 1.0000 | 0.00% | 0.00% [0.00-0.00] |
| pause_3 | 1.0000 | 0.00% | 0.00% [0.00-0.00] |
| splice_0.5 | 0.4943 | 50.28% | 98.33% [95.83-100.00] |
| splice_1 | 0.4693 | 54.17% | 95.00% [90.83-98.33] |
| splice_3 | 0.9660 | 9.17% | 25.83% [17.06-34.17] |

FRR at theta: 1.02% [0.56-1.62] over 120 calls x conditions.

Threshold over 50 speaker-disjoint splits: mean 0.400, sd 0.004, 95% range 0.392-0.407; test FRR mean 1.21% (95% range 0.23-2.55%).

## amr475 (operating threshold 0.505)

| Attack | AUC | EER | FAR at theta [95% CI] |
|---|---|---|---|
| full_asv | 0.9997 | 0.83% | 0.83% [0.00-2.50] |
| pause_3 | 1.0000 | 0.00% | 0.00% [0.00-0.00] |
| splice_0.5 | 0.4771 | 52.50% | 94.17% [90.00-97.50] |
| splice_1 | 0.5172 | 50.05% | 96.67% [93.33-99.17] |
| splice_3 | 0.8918 | 19.12% | 69.17% [60.83-76.67] |

FRR at theta: 1.02% [0.46-1.72] over 120 calls x conditions.

Threshold over 50 speaker-disjoint splits: mean 0.503, sd 0.005, 95% range 0.494-0.511; test FRR mean 1.16% (95% range 0.23-2.22%).

## g711a (operating threshold 0.204)

| Attack | AUC | EER | FAR at theta [95% CI] |
|---|---|---|---|
| full_asv | 1.0000 | 0.00% | 0.00% [0.00-0.00] |
| pause_3 | 1.0000 | 0.00% | 0.00% [0.00-0.00] |
| splice_0.5 | 0.5381 | 50.00% | 87.50% [81.67-92.50] |
| splice_1 | 0.9216 | 13.33% | 38.33% [30.83-46.27] |
| splice_3 | 1.0000 | 0.05% | 0.00% [0.00-0.00] |

FRR at theta: 1.02% [0.46-1.67] over 120 calls x conditions.

Threshold over 50 speaker-disjoint splits: mean 0.204, sd 0.005, 95% range 0.197-0.216; test FRR mean 1.35% (95% range 0.19-3.29%).

## g711u (operating threshold 0.206)

| Attack | AUC | EER | FAR at theta [95% CI] |
|---|---|---|---|
| full_asv | 1.0000 | 0.00% | 0.00% [0.00-0.00] |
| pause_3 | 1.0000 | 0.00% | 0.00% [0.00-0.00] |
| splice_0.5 | 0.6033 | 44.26% | 90.00% [83.33-95.00] |
| splice_1 | 0.9379 | 11.71% | 35.00% [26.67-43.77] |
| splice_3 | 1.0000 | 0.00% | 0.00% [0.00-0.00] |

FRR at theta: 1.02% [0.46-1.62] over 120 calls x conditions.

Threshold over 50 speaker-disjoint splits: mean 0.206, sd 0.003, 95% range 0.199-0.211; test FRR mean 1.28% (95% range 0.41-2.55%).

## opus16 (operating threshold 0.313)

| Attack | AUC | EER | FAR at theta [95% CI] |
|---|---|---|---|
| full_asv | 1.0000 | 0.00% | 0.00% [0.00-0.00] |
| pause_3 | 1.0000 | 0.00% | 0.00% [0.00-0.00] |
| splice_0.5 | 0.5029 | 49.12% | 95.00% [90.83-98.33] |
| splice_1 | 0.5739 | 44.21% | 90.83% [85.00-95.44] |
| splice_3 | 1.0000 | 0.65% | 0.00% [0.00-0.00] |

FRR at theta: 1.02% [0.46-1.67] over 120 calls x conditions.

Threshold over 50 speaker-disjoint splits: mean 0.314, sd 0.004, 95% range 0.307-0.320; test FRR mean 1.10% (95% range 0.41-2.04%).

**Opus diagnosis.** The 99th percentile rests on the top 11 of 1080 honest values: 0.314, 0.317, 0.319, 0.320, 0.320, 0.321, 0.322, 0.325, 0.327, 0.329, 0.335. Leave-one-speaker-out thresholds range 0.313-0.314; most influential speakers: spk13 (0.313), spk04 (0.313), spk06 (0.313).

