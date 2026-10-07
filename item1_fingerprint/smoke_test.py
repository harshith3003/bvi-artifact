"""
smoke_test.py — CODE CHECK ONLY. Builds an artificial 'speech-like' corpus
(pulse train through moving formants, with pauses) and runs run_ber.py --quick.
The numbers it produces are NOT results and must not be reported.
"""
import os, subprocess, sys
import numpy as np
from scipy.signal import lfilter

FS = 8000
root = sys.argv[1] if len(sys.argv) > 1 else "/tmp/bvi_smoke"
rng = np.random.default_rng(1)

def resonator(x, f, bw):
    r = np.exp(-np.pi * bw / FS); th = 2 * np.pi * f / FS
    return lfilter([1 - r], [1, -2 * r * np.cos(th), r * r], x)

def utterance(f0_mean, seconds):
    out = []
    while sum(len(o) for o in out) < seconds * FS:
        syl = int(rng.uniform(0.15, 0.3) * FS)
        f0 = f0_mean * rng.uniform(0.85, 1.15)
        t = np.arange(syl)
        pulses = (np.sin(2 * np.pi * np.cumsum(np.full(syl, f0 / FS))) > 0.97).astype(float)
        src = pulses + 0.02 * rng.normal(size=syl)
        F1, F2, F3 = rng.uniform(300, 800), rng.uniform(900, 2200), rng.uniform(2300, 3200)
        v = resonator(src, F1, 80) + 0.6 * resonator(src, F2, 120) + 0.3 * resonator(src, F3, 160)
        v *= np.hanning(syl)
        out.append(v)
        if rng.random() < 0.3:
            out.append(np.zeros(int(rng.uniform(0.2, 0.7) * FS)))
    x = np.concatenate(out)
    return 0.25 * x / (np.abs(x).max() + 1e-9)

def write(path, x):
    raw = path + ".raw"
    np.clip(x * 32767, -32768, 32767).astype(np.int16).tofile(raw)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", "8000", "-ac", "1", "-i", raw, path], check=True)
    os.remove(raw)

for s in range(6):
    d = os.path.join(root, "natural", f"spk{s}"); os.makedirs(d, exist_ok=True)
    for u in range(4):
        write(os.path.join(d, f"u{u}.wav"), utterance(100 + 25 * s, 6))
d = os.path.join(root, "synthetic"); os.makedirs(d, exist_ok=True)
for u in range(8):
    write(os.path.join(d, f"tts{u}.wav"), utterance(170, 6))
print("artificial corpus written to", root)
