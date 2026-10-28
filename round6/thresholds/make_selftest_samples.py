"""Writes SYNTHETIC ber_samples.csv shaped like the real data, only to test the analysis pipeline."""
import csv, random, sys
rng = random.Random(1)
MEAN = {"g711u": .06, "g711a": .06, "opus16": .17, "amr122": .26, "amr122_g711u": .25, "amr475": .35}
SEV = {"splice_0.5": .12, "splice_1": .2, "splice_3": .38, "full_asv": .5, "pause_3": .6}
conds = [f"{n}_loss{l}" for n in ("clean", "white20", "babble10") for l in (0, 1, 5)]
with open(sys.argv[1], "w", newline="") as f:
    w = csv.writer(f); w.writerow(["codec", "kind", "max_ber", "call_id", "speaker", "condition"])
    for cd, m in MEAN.items():
        for call in range(120):
            spk = f"spk{call % 40:02d}"; off = rng.gauss(0, .015)
            for cond in conds:
                w.writerow([cd, "honest", round(min(1, max(0, rng.gauss(m + .07 + off, .03))), 4), f"c{call}", spk, cond])
            for k, s in SEV.items():
                w.writerow([cd, k, round(min(1, max(0, rng.gauss(max(m + .07, s + m * .3), .05))), 4), f"c{call}", spk, "white20_loss1"])
