"""
test_pause_injection.py — 3 s of speech injected into a sender pause must make the call fail.

Scenario: the real caller talks, then listens in silence for 5 s, then talks again.
An in-path attacker injects 3 s of speech into the silent stretch. The sender's
activity bits say "silent"; the receiver hears clear speech -> pause violations.

Checks (G.711 mu-law channel, 1% packet loss):
  1. honest call (no injection)                        -> "pass"
  2. injected call with the v1.1 window rule            -> "fail"
  3. injected call with the old v1 rule (s_act only)    -> not "fail"  (documents the bug)

Audio: by default uses deterministic artificial voiced signals so the test runs
anywhere. With BVI_SPEECH_DIR=/path/to/LibriSpeech/test-clean it uses real speech
(first two speakers: caller and injected voice).

Run:  python3 test_pause_injection.py
"""
import os
import sys

import numpy as np

import channel as ch
import fingerprint as fp

THRESHOLD = 0.30   # any threshold below 1.0 gives the same verdicts here
FS = ch.FS


def artificial_speech(seconds, f0, seed):
    from scipy.signal import lfilter
    rng = np.random.default_rng(seed)

    def res(x, f, bw):
        r = np.exp(-np.pi * bw / FS); th = 2 * np.pi * f / FS
        return lfilter([1 - r], [1, -2 * r * np.cos(th), r * r], x)

    out = []
    while sum(len(o) for o in out) < seconds * FS:
        n = int(rng.uniform(0.15, 0.3) * FS)
        f = f0 * rng.uniform(0.85, 1.15)
        src = (np.sin(2 * np.pi * np.cumsum(np.full(n, f / FS))) > 0.97).astype(float) + 0.02 * rng.normal(size=n)
        v = res(src, rng.uniform(300, 800), 80) + 0.6 * res(src, rng.uniform(900, 2200), 120)
        out.append(v * np.hanning(n))
    x = np.concatenate(out)[: int(seconds * FS)]
    return 0.25 * x / (np.abs(x).max() + 1e-9)


def real_speech(root, speaker_index, seconds):
    spk = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))[speaker_index]
    files = sorted(os.path.join(dp, f) for dp, _, fs in os.walk(os.path.join(root, spk))
                   for f in fs if f.endswith(".flac"))
    buf = np.concatenate([ch.load_audio(f) for f in files[:10]])
    return buf[: int(seconds * FS)]


def dither(n, rng):
    return rng.normal(0, 10 ** (-70 / 20), n)


def verdict_for(sent, received, rng, old_rule=False):
    s_bits, s_act = fp.sender_fingerprint(sent)
    y = ch.packet_loss(ch.codec(received, "g711u"), 0.01, rng)
    r_bits, r_strong = fp.receiver_view(y)
    err, cnt, act = fp.frame_errors(s_bits, s_act, r_bits, r_strong)
    if old_rule:
        n = min(len(s_act), len(act))
        act = s_act[:n]                       # v1 behaviour: sender-active frames only
    wb = fp.window_bers(err, cnt, act)
    return fp.verdict(wb, THRESHOLD), wb


def main():
    rng = np.random.default_rng(20260909)
    root = os.environ.get("BVI_SPEECH_DIR")
    if root:
        talk1, talk2 = real_speech(root, 0, 8), real_speech(root, 0, 16)[8 * FS:]
        injected_voice = real_speech(root, 1, 3)
        source = f"real speech ({root})"
    else:
        talk1, talk2 = artificial_speech(8, 120, 1), artificial_speech(8, 120, 2)
        injected_voice = artificial_speech(3, 190, 3)
        source = "artificial voiced signal"

    pause = dither(5 * FS, rng)                         # caller listens for 5 s
    sent = np.concatenate([talk1, pause, talk2]) + dither(len(talk1) + len(pause) + len(talk2), rng)

    attacked = sent.copy()
    start = len(talk1) + 1 * FS                         # 1 s into the pause
    attacked[start: start + 3 * FS] += injected_voice   # 3 s of injected speech

    v_honest, _ = verdict_for(sent, sent, np.random.default_rng(1))
    v_new, wb_new = verdict_for(sent, attacked, np.random.default_rng(2))
    v_old, wb_old = verdict_for(sent, attacked, np.random.default_rng(2), old_rule=True)

    print(f"audio: {source}; channel: G.711 mu-law + 1% loss; threshold {THRESHOLD}")
    print(f"  honest call                         -> {v_honest}")
    print(f"  3 s injected into pause, current rule -> {v_new}  (max window BER {np.nanmax(wb_new):.3f})")
    print(f"  3 s injected into pause, old v1 rule  -> {v_old}  "
          f"(max conclusive window BER {np.nanmax(wb_old) if np.any(~np.isnan(wb_old)) else float('nan'):.3f})")

    ok = (v_honest == "pass") and (v_new == "fail") and (v_old != "fail")
    print("RESULT:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
