"""
fingerprint.py — BVI audio fingerprint, spec "bvi-fp-v1" (PROPOSED, needs sign-off
so the TIFS and SDLT papers use the same settings).

Per 20 ms frame the sender emits 17 bits:
  16 fingerprint bits  (sign of the time-difference of adjacent-band energy differences)
   1 activity bit      (speech gate, computed causally at the sender)
  => 17 bits x 50 frames/s = 850 bit/s

The receiver recomputes the 16 fingerprint bits from what it heard and compares:
  * frames the sender marked active: Hamming distance over the 16 bits
  * frames the sender marked SILENT but where the receiver hears clear speech:
    counted as 16 bit errors ("activity violation"); this closes the
    splice-into-a-pause hole that pure gating would open
  * frames silent on both sides: skipped (no evidence)
"""
import numpy as np

SPEC = {
    "version": "bvi-fp-v1.2",  # round 5: same spec; pause rule can be switched off for analysis
    "basis": "identical to experiments/digest/digest.py DigestParams() defaults "
             "(32 ms Hann, 20 ms hop, 17 Bark-spaced triangular bands 300-3400 Hz, "
             "pre-emphasis 0.97, log energies); activity bit and window rule added",
    "sample_rate_hz": 8000,
    "frame_hop_samples": 160,          # 20 ms, aligned with 20 ms RTP packetisation
    "window_samples": 256,             # 32 ms Hann analysis window
    "nfft": 256,
    "n_bands": 17,                     # -> 16 fingerprint bits per frame
    "band_lo_hz": 300.0,
    "band_hi_hz": 3400.0,
    "band_spacing": "Bark (Traunmuller), triangular, area-normalised",
    "pre_emphasis": 0.97,
    "bits_per_frame": 16,
    "activity_bits_per_frame": 1,
    "bitrate_bps": 850,                # fingerprint + activity; +64 bit/s auth tag, see digest_auth.py
    "gate_floor_window_s": 2.0,        # causal running minimum of smoothed frame level
    "gate_smooth_frames": 5,
    "gate_margin_db": 9.0,             # active if level >= floor + 9 dB ...
    "gate_abs_min_dbfs": -55.0,        # ... and >= -55 dBFS
    "violation_margin_db": 15.0,       # receiver 'clear speech' for activity violations
    "violation_min_run_frames": 5,     # v1.2: receiver speech must be sustained >= 100 ms ...
    "violation_sender_guard_frames": 2,  # ... where the sender was silent within +-40 ms
    "compare_window_frames": 100,      # 2 s decision windows
    "compare_hop_frames": 10,          # every 0.2 s
    "min_counted_frames_per_window": 40,  # sender-active OR violation frames (v1.1)
}

_FS = SPEC["sample_rate_hz"]
_HOP = SPEC["frame_hop_samples"]
_WIN = SPEC["window_samples"]
_NFFT = SPEC["nfft"]
_HANN = np.hanning(_WIN)


def _hz_to_bark(f):
    f = np.asarray(f, dtype=float)
    return (26.81 * f) / (1960.0 + f) - 0.53


def _bark_to_hz(b):
    b = np.asarray(b, dtype=float)
    return 1960.0 * (b + 0.53) / (26.28 - b)


def _filterbank():
    """Same triangular, area-normalised Bark filterbank as digest.py."""
    edges = _bark_to_hz(np.linspace(_hz_to_bark(SPEC["band_lo_hz"]), _hz_to_bark(SPEC["band_hi_hz"]),
                                    SPEC["n_bands"] + 1))
    freqs = np.fft.rfftfreq(_NFFT, 1.0 / _FS)
    fb = np.zeros((SPEC["n_bands"], len(freqs)))
    for m in range(SPEC["n_bands"]):
        lo, hi = edges[m], edges[m + 1]
        c = 0.5 * (lo + hi)
        rising = (freqs >= lo) & (freqs <= c)
        falling = (freqs > c) & (freqs <= hi)
        if c > lo:
            fb[m, rising] = (freqs[rising] - lo) / (c - lo)
        if hi > c:
            fb[m, falling] = (hi - freqs[falling]) / (hi - c)
        tot = fb[m].sum()
        if tot > 0:
            fb[m] /= tot
        else:
            fb[m, np.argmin(np.abs(freqs - c))] = 1.0
    return fb


_FB = _filterbank()


def _frames(x):
    """Frames starting at n*hop (as in digest.py), n = 0 .. 1 + (len-win)//hop - 1."""
    if len(x) < _WIN:
        x = np.pad(x, (0, _WIN - len(x)))
    n = 1 + (len(x) - _WIN) // _HOP
    idx = np.arange(_WIN)[None, :] + _HOP * np.arange(n)[:, None]
    return x[idx]


def analyse(x):
    """x: float array in [-1, 1] at 8 kHz.
    Returns (bits[n,16] bool, level_dbfs[n]). bits[n] compares frame n with n-1
    exactly as digest.digest_bits does (bits[0] is a placeholder, never active)."""
    x = np.asarray(x, dtype=np.float64)
    pe = np.append(x[0], x[1:] - SPEC["pre_emphasis"] * x[:-1])
    spec = np.abs(np.fft.rfft(_frames(pe) * _HANN, n=_NFFT, axis=1)) ** 2
    E = np.log(spec @ _FB.T + 1e-12)
    d_band = np.diff(E, axis=1)
    bits = np.zeros((E.shape[0], SPEC["bits_per_frame"]), dtype=bool)
    bits[1:] = np.diff(d_band, axis=0) > 0
    raw = _frames(x) * _HANN                            # level from the un-emphasised signal
    p = np.sum(raw ** 2, axis=1) / np.sum(_HANN ** 2)
    level = 10 * np.log10(p + 1e-12) + 3.01             # dBFS (full-scale sine = 0 dBFS)
    return bits, level


def gate(level, margin_db):
    """Causal speech gate: level above a running-minimum noise floor (last 2 s)."""
    k = SPEC["gate_smooth_frames"]
    sm = np.convolve(level, np.ones(k) / k, mode="full")[: len(level)]   # causal smoothing
    w = int(SPEC["gate_floor_window_s"] * _FS / _HOP)
    padded = np.concatenate([np.full(w - 1, np.inf), sm])
    floor = np.lib.stride_tricks.sliding_window_view(padded, w).min(axis=1)
    return (level >= floor + margin_db) & (level >= SPEC["gate_abs_min_dbfs"])


def sender_fingerprint(x):
    """What the sender commits/streams: 16 bits + 1 activity bit per frame."""
    bits, level = analyse(x)
    act = gate(level, SPEC["gate_margin_db"])
    act_bits = np.zeros_like(act)
    act_bits[1:] = act[1:] & act[:-1]                 # a bit-frame needs both frames voiced
    return bits, act_bits


def receiver_view(y):
    bits, level = analyse(y)
    strong = gate(level, SPEC["violation_margin_db"])
    return bits, strong


def _runs_at_least(mask, k):
    """True on frames that belong to a run of >= k consecutive True frames."""
    out = np.zeros_like(mask)
    n, i = len(mask), 0
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            if j - i >= k:
                out[i:j] = True
            i = j
        else:
            i += 1
    return out


def _dilate(mask, g):
    if g <= 0:
        return mask.copy()
    pad = np.concatenate([np.zeros(g, bool), mask, np.zeros(g, bool)])
    return np.lib.stride_tricks.sliding_window_view(pad, 2 * g + 1).any(axis=1)


def frame_errors(s_bits, s_act, r_bits, r_strong, pause_rule=True):
    """Per-frame (errors, counted_bits, counted_frames).

    v1.2 pause-violation rule: a frame is a violation only if the receiver hears
    SUSTAINED clear speech (run >= violation_min_run_frames) and the sender was
    silent within +- violation_sender_guard_frames. v1.1 counted single frames, so
    codec artefacts at word onsets and in near-silent pauses were scored as injected
    speech on honest calls."""
    n = min(len(s_bits), len(r_bits))
    s_bits, s_act, r_bits, r_strong = s_bits[:n], s_act[:n], r_bits[:n], r_strong[:n]
    ham = np.sum(s_bits != r_bits, axis=1)
    if not pause_rule:                          # analysis only: no pause violations at all
        return np.where(s_act, ham, 0), np.where(s_act, 16, 0), s_act.copy()
    sustained = _runs_at_least(r_strong, SPEC["violation_min_run_frames"])
    viol = (~_dilate(s_act, SPEC["violation_sender_guard_frames"])) & sustained
    err = np.where(s_act, ham, 0) + np.where(viol, 16, 0)
    cnt = np.where(s_act, 16, 0) + np.where(viol, 16, 0)
    # v1.1: a frame counts towards the window minimum if sender-active OR a violation
    return err, cnt, (s_act | viol)


def window_bers(err, cnt, act):
    """BER per 2 s window. `act` = sender-active OR violation frames (v1.1).
    NaN where the window has fewer than the minimum such frames."""
    W, H, M = SPEC["compare_window_frames"], SPEC["compare_hop_frames"], SPEC["min_counted_frames_per_window"]
    if len(err) < W:
        return np.array([np.nan])
    ce = np.concatenate([[0], np.cumsum(err)])
    cc = np.concatenate([[0], np.cumsum(cnt)])
    ca = np.concatenate([[0], np.cumsum(act.astype(int))])
    s = np.arange(0, len(err) - W + 1, H)
    e, c, a = ce[s + W] - ce[s], cc[s + W] - cc[s], ca[s + W] - ca[s]
    with np.errstate(invalid="ignore", divide="ignore"):
        ber = e / c
    ber[(a < M) | (c == 0)] = np.nan
    return ber


def verdict(wbers, threshold):
    conclusive = wbers[~np.isnan(wbers)]
    if conclusive.size == 0:
        return "unknown"
    return "fail" if np.any(conclusive > threshold) else "pass"
