"""
channel.py — telephone channel simulation for the fingerprint BER experiment.

Codecs run through ffmpeg (real encoders, not approximations):
  g711u    pcm_mulaw                     64 kbit/s
  g711a    pcm_alaw                      64 kbit/s
  opus16   libopus, 16 kbit/s, VoIP mode, 20 ms frames
  amr122   libopencore_amrnb 12.2 kbit/s  (needs an ffmpeg built with opencore-amr)
  amr475   libopencore_amrnb 4.75 kbit/s
  amr122_g711u   tandem: AMR-NB 12.2 then G.711 mu-law (typical mobile-to-PSTN path)

Packet loss is applied AFTER decoding, per 20 ms packet (Bernoulli), with simple
repetition concealment (the lost packet is replaced by the previous 20 ms).
Real decoders have their own concealment; this is stated as a limitation.
Background noise is added at the SENDER before encoding (it is part of what the
sender fingerprints), at a fixed SNR relative to the active-speech level.
"""
import os
import subprocess
import tempfile

import numpy as np

FS = 8000
PKT = 160  # 20 ms

CODECS = {
    "g711u": (["-c:a", "pcm_mulaw", "-f", "wav"], "wav"),
    "g711a": (["-c:a", "pcm_alaw", "-f", "wav"], "wav"),
    "opus16": (["-c:a", "libopus", "-b:a", "16k", "-application", "voip", "-frame_duration", "20"], "ogg"),
    "amr122": (["-c:a", "libopencore_amrnb", "-b:a", "12.2k"], "amr"),
    "amr475": (["-c:a", "libopencore_amrnb", "-b:a", "4.75k"], "amr"),
}
TANDEMS = {"amr122_g711u": ["amr122", "g711u"]}


def _run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def load_audio(path):
    """Any file ffmpeg can read -> float64 mono 8 kHz in [-1, 1]."""
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", str(FS), "-f", "s16le", "-"],
        check=True, capture_output=True).stdout
    return np.frombuffer(out, dtype=np.int16).astype(np.float64) / 32768.0


def _write_raw(x, path):
    np.clip(np.round(x * 32767), -32768, 32767).astype(np.int16).tofile(path)


def _codec_once(x, name, tmp):
    args, ext = CODECS[name]
    raw_in, enc, raw_out = (os.path.join(tmp, f) for f in ("in.raw", f"enc.{ext}", "out.raw"))
    _write_raw(x, raw_in)
    _run(["ffmpeg", "-v", "error", "-y", "-f", "s16le", "-ar", str(FS), "-ac", "1", "-i", raw_in,
          *args, "-ar", str(FS), enc])
    _run(["ffmpeg", "-v", "error", "-y", "-i", enc, "-ac", "1", "-ar", str(FS), "-f", "s16le", raw_out])
    y = np.fromfile(raw_out, dtype=np.int16).astype(np.float64) / 32768.0
    if len(y) < len(x):
        y = np.concatenate([y, np.zeros(len(x) - len(y))])
    return y[: len(x)]


def codec(x, name):
    with tempfile.TemporaryDirectory() as tmp:
        for step in TANDEMS.get(name, [name]):
            x = _codec_once(x, step, tmp)
    return x


def available_codecs():
    """Probe each codec with a short tone; return {name: True/False}."""
    t = np.arange(FS) / FS
    probe = 0.3 * np.sin(2 * np.pi * 440 * t)
    ok = {}
    for name in list(CODECS) + list(TANDEMS):
        try:
            codec(probe, name)
            ok[name] = True
        except Exception:
            ok[name] = False
    return ok


def ffmpeg_version():
    return subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True).stdout.splitlines()[0]


def packet_loss(y, rate, rng):
    if rate <= 0:
        return y.copy()
    y = y.copy()
    n = len(y) // PKT
    lost = rng.random(n) < rate
    for i in np.flatnonzero(lost):
        if i == 0:
            y[:PKT] = 0.0
        else:
            y[i * PKT:(i + 1) * PKT] = y[(i - 1) * PKT:i * PKT]
    return y


def speech_level(x):
    """Mean power over the louder half of 20 ms frames (rough active-speech level)."""
    n = len(x) // PKT
    p = np.mean(x[: n * PKT].reshape(n, PKT) ** 2, axis=1)
    return np.mean(np.sort(p)[n // 2:]) + 1e-12


def add_noise(x, noise, snr_db):
    noise = noise[: len(x)]
    if len(noise) < len(x):
        noise = np.resize(noise, len(x))
    g = np.sqrt(speech_level(x) / (np.mean(noise ** 2) + 1e-12) / 10 ** (snr_db / 10))
    return x + g * noise
