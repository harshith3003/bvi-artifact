"""Run the BVI version comparison and single-correction ablation.

Usage:
  python run_ablation.py --selftest                      # synthetic audio: checks the pipeline only, NOT results
  python run_ablation.py --ber-samples ber_samples.csv \\
         --thresholds thresholds.json --trials 2000       # real held-out BER samples: the paper's numbers

Outputs (results/<mode>/): per_trial.csv, summary.csv, tables.md, attack_success.png, honest_outcomes.png, run_info.json
"""
import argparse, csv, json, math, os, platform, random, statistics, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bvi6.harness import CONFIGS, scenarios, verify, ORG_A, ORG_A2
from bvi6.protocol import Org
from bvi6.route_policy_audio import EmpiricalOracle, SelfTestOracle, load_thresholds

def wilson(k, n, z=1.96):
    if n == 0: return (0.0, 0.0)
    p = k / n; d = 1 + z * z / n; c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--ber-samples"); ap.add_argument("--thresholds")
    ap.add_argument("--trials", type=int, default=1000); ap.add_argument("--seed", type=int, default=20260909)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if not a.selftest and not a.ber_samples:
        sys.exit("give --ber-samples (real data) or --selftest (pipeline check only)")
    mode = "selftest" if a.selftest else "empirical"
    out = a.out or os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", mode)
    os.makedirs(out, exist_ok=True)
    th = load_thresholds(a.thresholds)
    org = Org("did:bvi:example-bank", [ORG_A, ORG_A2])
    oracle = SelfTestOracle(random.Random()) if a.selftest else EmpiricalOracle(a.ber_samples, random.Random())
    sem = sorted({k for (_, k) in getattr(oracle, "s", {}) if k.startswith("semantic_")})
    for k in sem:                                   # every scenario codec must have samples for the edit
        missing = [c for c in ("g711u",) if (c, k) not in oracle.s]
        if missing: sys.exit(f"semantic kind {k} has no samples for {missing}")
    scen = scenarios(random.Random(a.seed), sem)
    rows, t_start = [], time.time()
    for si, (sname, (honest, factory)) in enumerate(scen.items()):
        for cfg in CONFIGS:
            for t in range(a.trials):
                call = factory(random.Random(f"{a.seed}|{si}|{t}|call"))
                call.scenario, call.honest = sname, honest
                call.build()
                oracle.rng = random.Random(f"{a.seed}|{si}|{t}|ber")      # identical audio draw for every config
                r = verify(cfg, call, org, oracle, th, None)
                rows.append(dict(config=cfg.name, scenario=sname, honest=honest, trial=t, **r))
        print(f"  {sname:58s} done", flush=True)
    with open(os.path.join(out, "per_trial.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

    # ---------------------------------------------------------------- summary
    summ = []
    for sname, (honest, _) in scen.items():
        for cfg in CONFIGS:
            rs = [r for r in rows if r["scenario"] == sname and r["config"] == cfg.name]; n = len(rs)
            cnt = lambda key, val: sum(1 for r in rs if r[key] == val)
            ver = cnt("final", "verified"); lo, hi = wilson(ver, n)
            summ.append(dict(scenario=sname, honest=honest, config=cfg.name, n=n,
                             verified=ver / n, verified_lo=lo, verified_hi=hi,
                             not_verified=cnt("final", "not verified") / n, fail=cnt("final", "fail") / n,
                             identity_fail=cnt("identity", "fail") / n,
                             route_pass=cnt("route", "pass") / n, route_bot=cnt("route", "bot") / n, route_fail=cnt("route", "fail") / n,
                             audio_pass=cnt("audio", "pass") / n, audio_fail=cnt("audio", "fail") / n,
                             audio_unverifiable=cnt("audio", "unverifiable") / n, audio_uncertain=cnt("audio", "uncertain") / n,
                             verify_ms_median=statistics.median(r["verify_ms"] for r in rs),
                             bytes_mean=statistics.mean(r["bytes"] for r in rs), reads_mean=statistics.mean(r["reads"] for r in rs)))
    with open(os.path.join(out, "summary.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(summ[0].keys())); w.writeheader(); w.writerows(summ)

    # ---------------------------------------------------------------- tables
    names = [c.name for c in CONFIGS]
    get = lambda s, c: next(x for x in summ if x["scenario"] == s and x["config"] == c)
    pct = lambda v: f"{100 * v:.1f}"
    L = [f"# BVI version comparison and ablation ({'SELFTEST: synthetic audio, NOT results' if a.selftest else 'empirical BER samples'})", "",
         f"Trials per cell: {a.trials}. Seed: {a.seed}. Thresholds: {json.dumps(th)}.", "",
         "## 1. Attack success (% of attack calls shown as VERIFIED; lower is better)", "",
         "| Attack | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for s, (h, _) in scen.items():
        if not h: L.append(f"| {s} | " + " | ".join(pct(get(s, c)["verified"]) for c in names) + " |")
    L += ["", "## 2. Honest calls: verified / not verified / fail (%)", "",
          "| Honest scenario | " + " | ".join(names) + " |", "|---|" + "---|" * len(names)]
    for s, (h, _) in scen.items():
        if h: L.append(f"| {s} | " + " | ".join(f"{pct(get(s,c)['verified'])} / {pct(get(s,c)['not_verified'])} / {pct(get(s,c)['fail'])}" for c in names) + " |")
    L += ["", "## 3. Layer outcomes for each attack (identity fail / route pass-bot-fail / audio fail; %)", ""]
    for s, (h, _) in scen.items():
        if h: continue
        L += [f"**{s}**", "", "| Config | identity fail | route pass | route no-evidence | route fail | audio fail | audio unverifiable | audio uncertain | final verified |", "|---|---|---|---|---|---|---|---|---|"]
        for c in names:
            x = get(s, c)
            L.append(f"| {c} | {pct(x['identity_fail'])} | {pct(x['route_pass'])} | {pct(x['route_bot'])} | {pct(x['route_fail'])} | {pct(x['audio_fail'])} | {pct(x['audio_unverifiable'])} | {pct(x['audio_uncertain'])} | {pct(x['verified'])} |")
        L.append("")
    L += ["## 4. Verification overhead (median over all scenarios)", "", "| Config | verify time (ms) | bytes per 30 s call | ledger reads |", "|---|---|---|---|"]
    for c in names:
        rs = [r for r in rows if r["config"] == c]
        L.append(f"| {c} | {statistics.median(r['verify_ms'] for r in rs):.3f} | {statistics.mean(r['bytes'] for r in rs):.0f} | {statistics.mean(r['reads'] for r in rs):.1f} |")
    open(os.path.join(out, "tables.md"), "w").write("\n".join(L) + "\n")

    # ---------------------------------------------------------------- plots
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt; import numpy as np
    att = [s for s, (h, _) in scen.items() if not h]
    M = np.array([[100 * get(s, c)["verified"] for c in names] for s in att])
    fig, ax = plt.subplots(figsize=(1.25 * len(names) + 4, 0.42 * len(att) + 1.6))
    im = ax.imshow(M, cmap="Reds", vmin=0, vmax=100, aspect="auto")
    ax.set_xticks(range(len(names))); ax.set_xticklabels(names, rotation=30, ha="right", fontsize=8)
    ax.set_yticks(range(len(att))); ax.set_yticklabels(att, fontsize=8)
    for i in range(len(att)):
        for j in range(len(names)): ax.text(j, i, f"{M[i,j]:.0f}", ha="center", va="center", fontsize=7, color="white" if M[i, j] > 60 else "black")
    ax.set_title(("SELFTEST (synthetic audio) - " if a.selftest else "") + "attack success: % verified", fontsize=10)
    plt.colorbar(im, fraction=0.03); plt.tight_layout(); plt.savefig(os.path.join(out, "attack_success.png"), dpi=180); plt.close()
    hon = [s for s, (h, _) in scen.items() if h]
    fig, axs = plt.subplots(1, len(hon), figsize=(3.2 * len(hon), 3.4), sharey=True)
    for ax, s in zip(axs, hon):
        v = [100 * get(s, c)["verified"] for c in names]; nv = [100 * get(s, c)["not_verified"] for c in names]; fl = [100 * get(s, c)["fail"] for c in names]
        x = np.arange(len(names)); ax.bar(x, v, color="#2e7d5b"); ax.bar(x, nv, bottom=v, color="#d9a441"); ax.bar(x, fl, bottom=np.array(v) + nv, color="#c23b4b")
        ax.set_xticks(x); ax.set_xticklabels(names, rotation=60, ha="right", fontsize=6); ax.set_title(s[:34], fontsize=7)
    axs[0].set_ylabel("% of honest calls (green verified, amber not verified, red fail)", fontsize=7)
    plt.tight_layout(); plt.savefig(os.path.join(out, "honest_outcomes.png"), dpi=170); plt.close()

    json.dump(dict(mode=mode, trials=a.trials, seed=a.seed, thresholds=th, configs=[c.__dict__ for c in CONFIGS],
                   python=sys.version.split()[0], platform=platform.platform(), seconds=round(time.time() - t_start, 1)),
              open(os.path.join(out, "run_info.json"), "w"), indent=2)
    print("wrote", out)

if __name__ == "__main__":
    main()
