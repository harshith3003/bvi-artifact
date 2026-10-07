"""
exposure_window.py — revocation exposure over the WHOLE period, L1 vs rollup.

Exposure starts when the key is stolen, not when revocation is submitted:

    exposure = D + T

    D = detection delay (theft -> someone notices and submits revocation)
    T = time until the revocation is trusted:
          L1 revocation   : T_L1 = Ethereum finality, 2 epochs = 2*32*12 s = 768 s (12.8 min)
                            (same finality rule X3 applies before trusting an anchor)
                            also reported with T_L1 = one 12 s block for reference
          rollup revocation, worst case (sequencer censors):
                            T_L2 = sequencing window, 3,600 L1 blocks = 12 h
                            (OP Stack Specification, "Configurability")

    ratio = (D + T_L2) / (D + T_L1)

No call rates, no dollar values: the ratio of exposure TIME is the only claim.
Outputs (revision/results/): exposure_window.csv, exposure_window.json, exposure_window.png
"""
import json
import os

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "results")
os.makedirs(OUT, exist_ok=True)

MIN = 60.0
HOUR = 3600.0
T_L2 = 3600 * 12.0            # sequencing window: 3,600 L1 blocks x 12 s
T_L1_FINAL = 2 * 32 * 12.0    # 2 epochs x 32 slots x 12 s = 768 s
T_L1_BLOCK = 12.0

D_LIST_H = [0, 0.25, 1, 6, 12, 24, 48, 72]


def ratio(D, t1):
    return (D + T_L2) / (D + t1)


def main():
    rows = []
    for dh in D_LIST_H:
        D = dh * HOUR
        rows.append({
            "detection_delay_h": dh,
            "exposure_L1_final_h": (D + T_L1_FINAL) / HOUR,
            "exposure_L2_worst_h": (D + T_L2) / HOUR,
            "ratio_vs_L1_finality": ratio(D, T_L1_FINAL),
            "ratio_vs_L1_one_block": ratio(D, T_L1_BLOCK),
        })

    with open(os.path.join(OUT, "exposure_window.csv"), "w") as fh:
        fh.write("detection_delay_h,exposure_L1_finality_h,exposure_L2_worst_h,ratio_vs_L1_finality,ratio_vs_L1_one_block\n")
        for r in rows:
            fh.write(f"{r['detection_delay_h']},{r['exposure_L1_final_h']:.4f},{r['exposure_L2_worst_h']:.4f},"
                     f"{r['ratio_vs_L1_finality']:.3f},{r['ratio_vs_L1_one_block']:.3f}\n")
    with open(os.path.join(OUT, "exposure_window.json"), "w") as fh:
        json.dump({"T_L2_seconds": T_L2, "T_L1_finality_seconds": T_L1_FINAL,
                   "T_L1_block_seconds": T_L1_BLOCK,
                   "sources": {
                       "sequencing_window": "OP Stack Specification, Configurability: 3,600 L1 blocks (12 h at 12 s)",
                       "finality": "Ethereum PoS: finalisation after 2 epochs of 32 slots x 12 s"},
                   "rows": rows}, fh, indent=2)

    D = np.linspace(0, 72 * HOUR, 400)
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(D / HOUR, (D + T_L2) / (D + T_L1_FINAL), label="L1 revocation trusted after finality (12.8 min)")
    ax.set_yscale("log")
    ax.set_xlabel("detection delay D: key theft to revocation submitted (hours)")
    ax.set_ylabel("exposure ratio, rollup worst case / L1")
    ax.set_title("Whole-period exposure ratio (D + 12 h) / (D + 12.8 min)")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "exposure_window.png"), dpi=150)

    print(f"{'D (h)':>6} | {'L1 exp (h)':>10} | {'L2 exp (h)':>10} | {'ratio (finality)':>16} | {'ratio (1 block)':>15}")
    print("-" * 70)
    for r in rows:
        print(f"{r['detection_delay_h']:>6} | {r['exposure_L1_final_h']:>10.2f} | {r['exposure_L2_worst_h']:>10.2f} | "
              f"{r['ratio_vs_L1_finality']:>16.2f} | {r['ratio_vs_L1_one_block']:>15.2f}")
    print("\nwrote exposure_window.csv, exposure_window.json, exposure_window.png")


if __name__ == "__main__":
    main()
