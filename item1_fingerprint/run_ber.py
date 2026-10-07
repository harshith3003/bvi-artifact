"""
run_ber.py — fingerprint bit error rate experiment (item 1).

Pipeline
  1. Build ~60 s "calls" per speaker from a natural-speech corpus (speaker = first
     sub-folder). Speakers are split (seeded) into CALIBRATION and TEST halves.
  2. Honest calls: every available codec x {clean, white 20 dB, babble 10 dB}
     x packet loss {0, 1%, 5%}. Sender fingerprints what it sends; receiver
     recomputes from what it heard; BER per 2 s window.
  3. Threshold: 99th percentile of the per-call maximum window BER over all
     CALIBRATION honest calls and conditions (target: <=1% of whole 60 s calls
     wrongly flagged). Then everything below is reported on TEST speakers only.
  4. Attacks (test speakers, clean source, 1% loss, every codec):
       full substitution, natural (another speaker) and synthetic (TTS)
       splice of L seconds, L in {0.5, 1, 2, 3, 5}, natural and synthetic
  5. Outputs raw per-call maxima too, so any table can be rebuilt at any threshold.

Usage
  python3 run_ber.py --natural DIR --synthetic DIR --out DIR [--jobs 8] [--quick]
"""
import argparse
import csv
import json
import os
import platform
import time
import zlib
from multiprocessing import Pool

import numpy as np

import channel as ch
import fingerprint as fp

SEED = 20260909
NOISES = ["clean", "white20", "babble10"]
LOSSES = [0.0, 0.01, 0.05]
SPLICE_S = [0.5, 1.0, 2.0, 3.0, 5.0]
AUDIO_EXT = (".flac", ".wav", ".aiff", ".aif", ".mp3", ".m4a", ".ogg")
GAP_S = 0.3
LISTEN_EVERY_S = 10.0          # after ~10 s of talking the caller listens ...
LISTEN_PAUSE_S = (3.0, 5.0)    # ... for 3-5 s of silence (pause-injection target)
PAUSE_INJECT_S = 3.0


# ── corpus ──────────────────────────────────────────────────────────────────
def audio_files(root):
    out = []
    for d, _, fs in os.walk(root):
        out += [os.path.join(d, f) for f in fs if f.lower().endswith(AUDIO_EXT)]
    return sorted(out)


def dither(n, rng):
    return rng.normal(0, 10 ** (-70 / 20), n)


def build_calls(natural_dir, call_s, per_speaker, max_speakers, rng):
    speakers = sorted(d for d in os.listdir(natural_dir) if os.path.isdir(os.path.join(natural_dir, d)))
    if max_speakers:
        speakers = speakers[:max_speakers]
    calls = []
    need = int(call_s * ch.FS)
    for spk in speakers:
        buf, made, talk = [], 0, 0.0
        for f in audio_files(os.path.join(natural_dir, spk)):
            u = ch.load_audio(f)
            buf += [u, dither(int(GAP_S * ch.FS), rng)]
            talk += len(u) / ch.FS
            if talk >= LISTEN_EVERY_S:                       # caller stops to listen
                buf.append(dither(int(rng.uniform(*LISTEN_PAUSE_S) * ch.FS), rng))
                talk = 0.0
            total = sum(len(b) for b in buf)
            if total >= need:
                x = np.concatenate(buf)
                calls.append({"speaker": spk, "x": x[:need] + dither(need, rng)})
                buf, made, talk = [], made + 1, 0.0
                if made >= per_speaker:
                    break
        print(f"  speaker {spk}: {made} call(s)", flush=True)
    return calls


def synthetic_stream(synth_dir, rng):
    files = audio_files(synth_dir)
    rng.shuffle(files)
    parts = []
    for f in files:
        parts += [ch.load_audio(f), dither(int(GAP_S * ch.FS), rng)]
    return np.concatenate(parts), len(files)


# ── comparison ──────────────────────────────────────────────────────────────
def xcorr_lag(x, y, max_lag=800):
    n = 1 << int(np.ceil(np.log2(len(x) + len(y))))
    c = np.fft.irfft(np.fft.rfft(y, n) * np.conj(np.fft.rfft(x, n)), n)
    lags = np.concatenate([np.arange(0, max_lag + 1), np.arange(-max_lag, 0)])
    vals = np.concatenate([c[: max_lag + 1], c[-max_lag:]])
    return int(lags[np.argmax(vals)])


def compare(s_bits, s_act, x_sent, y):
    """Returns (window BERs with pause rule, window BERs without it, whole-call BER with it).
    Each rule picks its own best +-2-frame alignment, as before."""
    lag = xcorr_lag(x_sent, y)
    y = np.roll(y, -lag)
    r_bits, r_strong = fp.receiver_view(y)
    out = {}
    for rule in (True, False):
        best = None
        for sh in range(-2, 3):
            err, cnt, act = fp.frame_errors(s_bits, s_act, np.roll(r_bits, sh, axis=0), np.roll(r_strong, sh),
                                            pause_rule=rule)
            tot = err.sum() / max(cnt.sum(), 1)
            if best is None or tot < best[0]:
                best = (tot, err, cnt, act)
        out[rule] = (fp.window_bers(best[1], best[2], best[3]), best[0])
    return out[True][0], out[False][0], out[True][1]


def summarise(wb):
    c = wb[~np.isnan(wb)]
    return (float(c.max()) if c.size else float("nan")), int(c.size)


# ── workers ─────────────────────────────────────────────────────────────────
def benign_task(args):
    i, call, codecs, babble_srcs, seed = args
    rng = np.random.default_rng([seed, 1, i])
    x = call["x"]
    rows, windows = [], {}
    for noise in NOISES:
        if noise == "clean":
            sent = x
        elif noise == "white20":
            sent = ch.add_noise(x, rng.normal(0, 1, len(x)), 20)
        else:
            sent = ch.add_noise(x, sum(babble_srcs), 10)
        s_bits, s_act = fp.sender_fingerprint(sent)
        for cname in codecs:
            y = ch.codec(sent, cname)
            for loss in LOSSES:
                wb, wb_off, whole = compare(s_bits, s_act, sent, ch.packet_loss(y, loss, rng))
                mx, nconc = summarise(wb)
                mx_off, nconc_off = summarise(wb_off)
                rows.append([call["speaker"], i, cname, noise, loss, whole, mx, nconc, int(s_act.sum()),
                             mx_off, nconc_off])
                windows[(cname, noise, loss)] = wb
    return rows, windows


def splice(x, sub, start_s, length_s, rng):
    y = x.copy()
    a, n = int(start_s * ch.FS), int(length_s * ch.FS)
    # take the inserted segment from a well-voiced part of the substitute audio
    _, sub_act = fp.sender_fingerprint(sub)
    fr = n // fp.SPEC["frame_hop_samples"]
    best, off = -1, 0
    for _ in range(20):
        o = int(rng.integers(0, len(sub) - n))
        f0 = o // fp.SPEC["frame_hop_samples"]
        v = sub_act[f0: f0 + fr].mean() if fr else 0
        if v > best:
            best, off = v, o
    seg = sub[off: off + n].copy()
    xf = int(0.01 * ch.FS)
    ramp = np.linspace(0, 1, xf)
    seg[:xf] = seg[:xf] * ramp + y[a: a + xf] * (1 - ramp)
    seg[-xf:] = seg[-xf:] * (1 - ramp) + y[a + n - xf: a + n] * ramp
    y[a: a + n] = seg
    return y


def longest_pause(s_act, min_frames):
    """(start_frame, length) of the longest run of sender-inactive frames, or None."""
    best, run_start, best_len = None, None, 0
    for f, a in enumerate(list(s_act) + [True]):
        if not a and run_start is None:
            run_start = f
        elif a and run_start is not None:
            if f - run_start > best_len:
                best, best_len = run_start, f - run_start
            run_start = None
    return (best, best_len) if best is not None and best_len >= min_frames else None


def voiced_segment(sub, n, rng):
    _, act = fp.sender_fingerprint(sub)
    hop = fp.SPEC["frame_hop_samples"]
    best, off = -1, 0
    for _ in range(20):
        o = int(rng.integers(0, len(sub) - n))
        v = act[o // hop: (o + n) // hop].mean()
        if v > best:
            best, off = v, o
    return sub[off: off + n].copy()


def attack_task(args):
    i, call, cname, natural_sub, synth_sub, synth2_sub, seed = args
    rng = np.random.default_rng([seed, 2, i, zlib.crc32(cname.encode())])
    x = call["x"]
    T = len(x) / ch.FS
    s_bits, s_act = fp.sender_fingerprint(x)
    rows = []

    def run(kind, received_src, length, overlap):
        y = ch.packet_loss(ch.codec(received_src, cname), 0.01, rng)
        wb, wb_off, whole = compare(s_bits, s_act, x, y)
        mx, nconc = summarise(wb)
        mx_off, nconc_off = summarise(wb_off)
        rows.append([call["speaker"], i, cname, kind, length, whole, mx, nconc, overlap, mx_off, nconc_off])

    sources = [("natural", natural_sub), ("synthetic", synth_sub)]
    if synth2_sub is not None:
        sources.append(("synthetic_say", synth2_sub))
    for tag, sub in sources:
        run(f"full_{tag}", sub[: len(x)], T, 1.0)
    for L in SPLICE_S:
        for tag, sub in sources:
            start = float(rng.uniform(2.0, T - 2.0 - L))
            f0 = int(start * ch.FS) // fp.SPEC["frame_hop_samples"]
            overlap = float(s_act[f0: f0 + int(L * 50)].mean())   # share of splice over sender speech
            run(f"splice_{tag}", splice(x, sub, start, L, rng), L, overlap)
    # pause injection: 3 s of speech into the longest sender pause (the caller is listening)
    hop = fp.SPEC["frame_hop_samples"]
    n = int(PAUSE_INJECT_S * ch.FS)
    p = longest_pause(s_act, int(PAUSE_INJECT_S * 50) + 10)
    if p is not None:
        start = p[0] * hop + 5 * hop
        for tag, sub in sources:
            y = x.copy()
            y[start: start + n] = voiced_segment(sub, n, rng)
            run(f"pause_inject_{tag}", y, PAUSE_INJECT_S, 0.0)
    return rows


# ── stats ───────────────────────────────────────────────────────────────────
def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def write_csv(path, header, rows):
    with open(path, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--natural", required=True)
    ap.add_argument("--synthetic", required=True, help="main synthetic source (ASVspoof 2019 LA spoofed speech)")
    ap.add_argument("--synthetic-secondary", default=None, help="optional secondary synthetic source (macOS say)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--call-seconds", type=float, default=60.0)
    ap.add_argument("--calls-per-speaker", type=int, default=3)
    ap.add_argument("--max-speakers", type=int, default=0)
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 1))
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--quick", action="store_true", help="code check only: few speakers, short calls")
    a = ap.parse_args()
    if a.quick:
        a.call_seconds, a.calls_per_speaker, a.max_speakers = 20.0, 1, a.max_speakers or 6
    os.makedirs(a.out, exist_ok=True)
    rng = np.random.default_rng(a.seed)
    t0 = time.time()

    print("Probing codecs ...", flush=True)
    avail = ch.available_codecs()
    codecs = [c for c, ok in avail.items() if ok]
    for c, ok in avail.items():
        print(f"  {c:14s} {'OK' if ok else 'NOT AVAILABLE in this ffmpeg build'}")

    print("Building calls ...", flush=True)
    calls = build_calls(a.natural, a.call_seconds, a.calls_per_speaker, a.max_speakers, rng)
    synth, n_synth_files = synthetic_stream(a.synthetic, rng)
    synth2, n_synth2_files = (synthetic_stream(a.synthetic_secondary, rng) if a.synthetic_secondary else (None, 0))
    speakers = sorted({c["speaker"] for c in calls})
    order = list(rng.permutation(speakers))
    calib_spk = set(order[: len(order) // 2])
    calib = [i for i, c in enumerate(calls) if c["speaker"] in calib_spk]
    test = [i for i, c in enumerate(calls) if c["speaker"] not in calib_spk]
    print(f"  {len(calls)} calls, {len(speakers)} speakers: {len(calib)} calibration / {len(test)} test calls")

    # babble sources: three calls from OTHER speakers, fixed per call
    def babble_for(i):
        others = [j for j, c in enumerate(calls) if c["speaker"] != calls[i]["speaker"]]
        pick = np.random.default_rng([a.seed, 3, i]).choice(others, size=min(3, len(others)), replace=False)
        return [calls[j]["x"] for j in pick]

    print("Honest calls ...", flush=True)
    tasks = [(i, calls[i], codecs, babble_for(i), a.seed) for i in range(len(calls))]
    with Pool(a.jobs) as pool:
        results = pool.map(benign_task, tasks)
    benign_rows = [r for rows, _ in results for r in rows]
    write_csv(os.path.join(a.out, "honest_raw.csv"),
              ["speaker", "call", "codec", "noise", "loss", "whole_call_ber", "max_window_ber",
               "conclusive_windows", "sender_active_frames", "max_window_ber_nopause",
               "conclusive_windows_nopause"], benign_rows)

    # threshold from calibration speakers only
    calib_max = np.array([r[6] for r in benign_rows if r[1] in calib and not np.isnan(r[6])])
    theta = float(np.quantile(calib_max, 0.99))
    per_cond_q99 = {}
    for cname in codecs:
        for noise in NOISES:
            for loss in LOSSES:
                v = [r[6] for r in benign_rows if r[1] in calib and r[2] == cname and r[3] == noise
                     and r[4] == loss and not np.isnan(r[6])]
                if v:
                    per_cond_q99[f"{cname}|{noise}|{loss}"] = float(np.quantile(v, 0.99))
    print(f"  threshold (99th pct of calibration per-call max window BER) = {theta:.4f}")

    # honest results on TEST speakers
    honest_summary = []
    for cname in codecs:
        for noise in NOISES:
            for loss in LOSSES:
                sel = [(r, results[r[1]][1][(cname, noise, loss)]) for r in benign_rows
                       if r[1] in test and r[2] == cname and r[3] == noise and r[4] == loss]
                n = len(sel)
                flagged = sum(1 for r, _ in sel if not np.isnan(r[6]) and r[6] > theta)
                unknown = sum(1 for r, _ in sel if r[7] == 0)
                wins = np.concatenate([w[~np.isnan(w)] for _, w in sel]) if sel else np.array([])
                lo, hi = wilson(flagged, n)
                honest_summary.append([cname, noise, loss, n,
                                       round(float(np.mean([r[5] for r, _ in sel])), 5),
                                       round(float(np.median(wins)), 5) if wins.size else "",
                                       round(float(np.quantile(wins, 0.99)), 5) if wins.size else "",
                                       round(flagged / n, 5) if n else "", round(lo, 5), round(hi, 5),
                                       round(float((wins > theta).mean()), 6) if wins.size else "",
                                       unknown])
    write_csv(os.path.join(a.out, "honest_summary.csv"),
              ["codec", "noise", "loss", "test_calls", "mean_whole_call_ber", "median_window_ber",
               "p99_window_ber", "call_false_flag_rate", "ci95_lo", "ci95_hi",
               "per_window_false_flag_rate", "calls_unknown"], honest_summary)

    print("Attacks ...", flush=True)
    test_calls = [calls[i] for i in test]
    atasks = []
    for k, i in enumerate(test):
        other = [j for j in test if calls[j]["speaker"] != calls[i]["speaker"]] or [j for j in range(len(calls)) if j != i]
        nat = calls[int(np.random.default_rng([a.seed, 4, i]).choice(other))]["x"]
        need = len(calls[i]["x"])
        off = (k * need) % max(1, len(synth) - need)
        syn = np.resize(synth[off: off + need], need)
        syn2 = None
        if synth2 is not None:
            off2 = (k * need) % max(1, len(synth2) - need)
            syn2 = np.resize(synth2[off2: off2 + need], need)
        for cname in codecs:
            atasks.append((i, calls[i], cname, nat, syn, syn2, a.seed))
    with Pool(a.jobs) as pool:
        arows = [r for rows in pool.map(attack_task, atasks) for r in rows]
    write_csv(os.path.join(a.out, "attack_raw.csv"),
              ["speaker", "call", "codec", "attack", "length_s", "whole_call_ber", "max_window_ber",
               "conclusive_windows", "share_over_sender_speech", "max_window_ber_nopause",
               "conclusive_windows_nopause"], arows)

    attack_summary, shortest = [], []
    for cname in codecs:
        for kind in sorted({r[3] for r in arows}):
            lengths = sorted({r[4] for r in arows if r[2] == cname and r[3] == kind})
            det_by_L = {}
            for L in lengths:
                sel = [r for r in arows if r[2] == cname and r[3] == kind and r[4] == L]
                n = len(sel)
                k = sum(1 for r in sel if not np.isnan(r[6]) and r[6] > theta)
                lo, hi = wilson(k, n)
                det_by_L[L] = k / n if n else 0
                attack_summary.append([cname, kind, L if not kind.startswith("full") else "full", n,
                                       round(float(np.mean([r[5] for r in sel])), 5),
                                       round(k / n, 5) if n else "", round(lo, 5), round(hi, 5)])
            if kind.startswith("splice"):
                s95 = min([L for L, d in det_by_L.items() if d >= 0.95], default=None)
                s50 = min([L for L, d in det_by_L.items() if d >= 0.50], default=None)
                shortest.append([cname, kind, s95 if s95 is not None else f">{max(SPLICE_S)}",
                                 s50 if s50 is not None else f">{max(SPLICE_S)}"])
    write_csv(os.path.join(a.out, "attack_summary.csv"),
              ["codec", "attack", "splice_length_s", "test_calls", "mean_whole_call_ber",
               "detection_rate", "ci95_lo", "ci95_hi"], attack_summary)
    write_csv(os.path.join(a.out, "shortest_splice.csv"),
              ["codec", "attack", "shortest_L_detected_ge_95pct", "shortest_L_detected_ge_50pct"], shortest)

    manifest = {
        "spec": fp.SPEC, "seed": a.seed, "threshold": theta,
        "threshold_rule": "99th percentile of per-call max 2 s-window BER, calibration speakers, all honest conditions pooled",
        "per_condition_calibration_q99": per_cond_q99,
        "codecs_available": avail, "ffmpeg": ch.ffmpeg_version(),
        "natural_corpus": os.path.abspath(a.natural), "synthetic_corpus": os.path.abspath(a.synthetic),
        "synthetic_files": n_synth_files, "call_seconds": a.call_seconds,
        "synthetic_secondary_corpus": os.path.abspath(a.synthetic_secondary) if a.synthetic_secondary else None,
        "synthetic_secondary_files": n_synth2_files,
        "listening_pauses": {"every_s": LISTEN_EVERY_S, "pause_s": LISTEN_PAUSE_S},
        "pause_injection_s": PAUSE_INJECT_S,
        "calls": len(calls), "speakers": len(speakers),
        "calibration_speakers": sorted(calib_spk), "test_calls": len(test), "calibration_calls": len(calib),
        "noises": NOISES, "losses": LOSSES, "splice_lengths_s": SPLICE_S,
        "attack_channel": "clean source, 1% packet loss",
        "packet_loss_model": "Bernoulli per 20 ms packet, after decoding, repetition concealment",
        "quick_mode": a.quick, "numpy": np.__version__, "python": platform.python_version(),
        "machine": platform.platform(), "processor": platform.processor(),
        "runtime_s": round(time.time() - t0, 1),
    }
    with open(os.path.join(a.out, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.2))
        hm = np.array([r[6] for r in benign_rows if r[1] in test and not np.isnan(r[6])])
        for lab, vals in [("honest (all conditions)", hm),
                          ("full substitution, natural", [r[6] for r in arows if r[3] == "full_natural"]),
                          ("full substitution, synthetic", [r[6] for r in arows if r[3] == "full_synthetic"])]:
            ax1.hist(np.array(vals, dtype=float), bins=40, alpha=0.55, label=lab, density=True)
        ax1.axvline(theta, color="k", ls="--", label=f"threshold {theta:.3f}")
        ax1.set_xlabel("max 2 s-window BER per call")
        ax1.set_title("Honest vs substituted calls (test speakers)")
        ax1.legend(fontsize=7)
        for cname in codecs:
            for kind, ls in (("splice_natural", "-"), ("splice_synthetic", "--")):
                if not any(r[1] == kind for r in attack_summary):
                    continue
                rows = [r for r in attack_summary if r[0] == cname and r[1] == kind]
                ax2.plot([r[2] for r in rows], [r[5] for r in rows], ls, marker="o", label=f"{cname} {kind[7:]}")
        ax2.set_xlabel("splice length (s)")
        ax2.set_ylabel("detection rate")
        ax2.set_title("Splice detection at the chosen threshold")
        ax2.legend(fontsize=6, ncol=2)
        ax2.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(os.path.join(a.out, "ber_figure.png"), dpi=150)
    except Exception as e:
        print("figure skipped:", e)

    print(f"\nDone in {manifest['runtime_s']} s. Threshold = {theta:.4f}. Results in {a.out}")
    print("Shortest splice detected (>=95% | >=50%):")
    for r in shortest:
        print(f"  {r[0]:14s} {r[1]:17s} {r[2]} | {r[3]}")


if __name__ == "__main__":
    main()
