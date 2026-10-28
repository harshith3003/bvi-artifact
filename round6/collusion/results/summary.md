# Item 4: collusion and participation sweep

Trials per cell: 200,000; seed 20260909. Max |Monte Carlo - closed form| (positional, random): 0.0046.

Detection is over feasible attacks (at least one corrupt carrier). Route layer only: with number binding (BVI-R, BVI-B), the identity layer catches every calling-number rewrite regardless of these rates.

| H | c | p | P(attack feasible) | BVI-0 random | theory | BVI-0 targeted | BVI-R random | BVI-R targeted | BVI-0 + launderer |
|---|---|---|---|---|---|---|---|---|---|
| 5 | 0.1 | 0.5 | 0.409 | 0.263 | 0.265 | 0.246 | 0.052 | 0.051 | 0 |
| 5 | 0.1 | 1.0 | 0.410 | 0.576 | 0.576 | 0.535 | 0.345 | 0.336 | 0 |
| 5 | 0.25 | 0.5 | 0.763 | 0.223 | 0.224 | 0.186 | 0.039 | 0.037 | 0 |
| 5 | 0.25 | 1.0 | 0.763 | 0.521 | 0.522 | 0.425 | 0.259 | 0.242 | 0 |
| 12 | 0.1 | 0.5 | 0.716 | 0.646 | 0.646 | 0.539 | 0.277 | 0.230 | 0 |
| 12 | 0.1 | 1.0 | 0.717 | 0.823 | 0.822 | 0.736 | 0.723 | 0.623 | 0 |
| 12 | 0.25 | 0.5 | 0.968 | 0.590 | 0.591 | 0.339 | 0.201 | 0.120 | 0 |
| 12 | 0.25 | 1.0 | 0.968 | 0.793 | 0.793 | 0.549 | 0.640 | 0.402 | 0 |
